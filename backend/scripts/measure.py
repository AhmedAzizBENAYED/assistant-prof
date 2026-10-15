"""Walking-skeleton measurement (``just measure``, T-006, ADR-035, ADR-039).

Measures, against the ARCHITECTURE §2 budgets:

- the size of the packaged backend (PyInstaller onedir) and of the desktop shell executable;
- cold start: time until the first authorised ``/health`` 200, for the backend alone and for
  the whole app (the shell reports it as a ``backend_healthy`` line on its stdout);
- idle memory once started: RSS and USS of each process and in total. Budgets are judged on USS
  because summed RSS counts memory shared between processes (WebView2) several times.

Both are measured for two kinds of start (ADR-040): a **new database** (first launch, or the
first start after an update: Alembic migrates), each run in a fresh temporary data directory;
and a **database at head** (the everyday start, fast path), all runs in one temporary data
directory seeded by an untimed start. The real user data is never touched. After each whole-app
run the shell is killed and the script checks that the backend exits by itself (parent-death
detection through stdin, ADR-038). The report goes to ``docs/reports/``.
"""

import argparse
import importlib
import io
import json
import os
import platform
import queue
import secrets
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import IO, Literal

import psutil
from pydantic import BaseModel, ValidationError

from assistant_prof.core.paths import DataPaths
from assistant_prof.persistence.migrate import HEAD_REVISION, read_revision

MB = 1024 * 1024
BACKEND_RSS_BUDGET_MB = 250  # ARCH §2, judged on USS
APP_RSS_BUDGET_MB = 450  # ARCH §2, judged on USS
COLD_START_BUDGET_S = 6.0  # ARCH §2, on a 4-core 2015-era CPU
INSTALLER_BUDGET_MB = 150  # ARCH §16, measured on the installer in T-803
STARTUP_TIMEOUT_S = 60.0
EXIT_TIMEOUT_S = 10.0
HEALTH_POLL_S = 0.02


class MeasureError(Exception):
    """A run did not behave as the startup contract says."""


class ShellEvent(BaseModel):
    """The JSON line the desktop shell prints on stdout once the backend is healthy or failed."""

    event: Literal["backend_healthy", "backend_failed"]
    elapsed_ms: int | None = None
    port: int | None = None
    backend_pid: int | None = None
    version: str | None = None
    error: str | None = None


def parse_shell_event(line: str) -> ShellEvent:
    """Parse the shell's stdout line; raise ``MeasureError`` if it is not one of its events."""
    try:
        return ShellEvent.model_validate_json(line)
    except ValidationError as exc:
        raise MeasureError(f"unexpected line from the shell: {line.strip()!r}") from exc


@dataclass(frozen=True)
class Stat:
    """First run (closest to a cold start) and median of the runs."""

    first: float
    median: float
    minimum: float
    maximum: float


def summarise(values: Sequence[float]) -> Stat:
    """Summarise per-run values; the first run is kept apart (cold file cache, AV scan)."""
    if not values:
        raise ValueError("no values to summarise")
    return Stat(values[0], statistics.median(values), min(values), max(values))


@dataclass(frozen=True)
class ProcessMemory:
    """Idle memory of one process, in bytes. ``uss`` is None if the OS refused to tell."""

    name: str
    rss: int
    uss: int | None


@dataclass(frozen=True)
class MemoryTotal:
    """Summed memory of a group of processes, in bytes."""

    rss: int
    uss: int | None  # None if any process's USS is unknown: never under-report


def total(processes: Sequence[ProcessMemory]) -> MemoryTotal:
    """Sum RSS and USS over ``processes``."""
    uss_values = [p.uss for p in processes]
    known = [u for u in uss_values if u is not None]
    return MemoryTotal(
        rss=sum(p.rss for p in processes),
        uss=sum(known) if len(known) == len(uss_values) else None,
    )


def group_by_name(processes: Sequence[ProcessMemory]) -> list[tuple[str, int, MemoryTotal]]:
    """Group processes by executable name: (name, count, total), largest USS first."""
    names = sorted({p.name for p in processes})
    groups = [
        (name, len(members), total(members))
        for name in names
        for members in [[p for p in processes if p.name == name]]
    ]
    return sorted(groups, key=lambda g: -(g[2].uss if g[2].uss is not None else g[2].rss))


def verdict(value: float | None, budget: float) -> str:
    """Return ``pass`` or ``FAIL`` against an upper budget; ``n/a`` if unknown."""
    if value is None:
        return "n/a"
    return "pass" if value < budget else "FAIL"


def dir_size(root: Path) -> tuple[int, int]:
    """Return (total bytes, file count) of the regular files under ``root``."""
    files = [p for p in root.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files)


@dataclass(frozen=True)
class Machine:
    """Where the measurement ran."""

    cpu: str
    cores: int | None
    threads: int | None
    ram_bytes: int
    os: str
    python: str
    commit: str


@dataclass
class BackendSamples:
    """Per-run figures of the backend started alone."""

    ready_s: list[float] = field(default_factory=list)
    health_s: list[float] = field(default_factory=list)
    memory: list[ProcessMemory] = field(default_factory=list)


@dataclass
class AppSamples:
    """Per-run figures of the whole app."""

    health_s: list[float] = field(default_factory=list)
    shell_reported_s: list[float] = field(default_factory=list)
    memory: list[list[ProcessMemory]] = field(default_factory=list)


@dataclass
class Report:
    """Everything the markdown report shows, for both kinds of start (new database, at head)."""

    machine: Machine
    runs: int
    idle_seconds: float
    backend_bundle_bytes: int
    backend_bundle_files: int
    shell_exe_bytes: int
    backend_new_db: BackendSamples = field(default_factory=BackendSamples)
    backend_at_head: BackendSamples = field(default_factory=BackendSamples)
    app_new_db: AppSamples = field(default_factory=AppSamples)
    app_at_head: AppSamples = field(default_factory=AppSamples)
    orphan_checks: list[bool] = field(default_factory=list)


def _mb(value: float | None) -> str:
    return "n/a" if value is None else f"{value / MB:.1f}"


def _s(stat: Stat) -> str:
    return f"{stat.first:.2f} | {stat.median:.2f} | {stat.minimum:.2f} to {stat.maximum:.2f}"


def _median_memory(samples: Sequence[MemoryTotal]) -> MemoryTotal:
    uss = [s.uss for s in samples]
    return MemoryTotal(
        rss=int(statistics.median(s.rss for s in samples)),
        uss=None if None in uss else int(statistics.median(u for u in uss if u is not None)),
    )


def _start_row(label: str, seconds: float) -> str:
    return (
        f"| Cold start, whole app, {label} | {seconds:.2f} s | < {COLD_START_BUDGET_S:g} s "
        f"| {verdict(seconds, COLD_START_BUDGET_S)} |"
    )


def _memory_row(label: str, memory: MemoryTotal, budget_mb: int) -> str:
    return (
        f"| Idle memory, {label} | {_mb(memory.uss)} MB | < {budget_mb} MB "
        f"| {verdict(_mb_value(memory.uss), budget_mb)} |"
    )


def render_report(report: Report, today: date) -> str:
    """Render the report as markdown; each figure is given for both kinds of start."""
    m = report.machine
    new_backend, head_backend = report.backend_new_db, report.backend_at_head
    new_app, head_app = report.app_new_db, report.app_at_head
    app_health = summarise(new_app.health_s)
    head_app_health = summarise(head_app.health_s)
    backend_idle = _median_memory([total([p]) for p in new_backend.memory])
    head_backend_idle = _median_memory([total([p]) for p in head_backend.memory])
    app_idle = _median_memory([total(run) for run in new_app.memory])
    head_app_idle = _median_memory([total(run) for run in head_app.memory])
    bundle_total = report.backend_bundle_bytes + report.shell_exe_bytes
    orphans = sum(not ok for ok in report.orphan_checks)
    last_run = new_app.memory[-1]
    timings = [
        ("Backend alone: spawn → ready line", new_backend.ready_s, head_backend.ready_s),
        (
            "Backend alone: spawn → first authorised `/health` 200",
            new_backend.health_s,
            head_backend.health_s,
        ),
        (
            "Whole app: launch → shell reports `/health` 200 (measured by this script)",
            new_app.health_s,
            head_app.health_s,
        ),
        (
            "Whole app: same, as timed inside the shell",
            new_app.shell_reported_s,
            head_app.shell_reported_s,
        ),
    ]
    memories = [
        ("Backend alone (median of runs)", "1", backend_idle, head_backend_idle),
        ("Whole app (median of runs)", "all", app_idle, head_app_idle),
    ]

    lines = [
        f"# Walking-skeleton measurement, {today.isoformat()}",
        "",
        "Generated by `just measure` (T-006, ADR-035, ADR-039, ADR-040). Budgets from "
        "ARCHITECTURE §2.",
        "",
        "## Machine",
        "",
        f"- CPU: {m.cpu} ({m.cores} cores, {m.threads} threads)",
        f"- RAM: {m.ram_bytes / (1024 * MB):.1f} GB",
        f"- OS: {m.os}",
        f"- Python (packaged backend): {m.python}",
        f"- Commit: `{m.commit}`",
        f"- Runs: {report.runs} per kind of start; idle wait before memory samples: "
        f"{report.idle_seconds:g} s",
        "",
        "## Summary against the budgets",
        "",
        "*New database*: first launch, or first start after an update (migrations run). "
        "*Database at head*: the everyday start.",
        "",
        "| Measure | Value | Budget | Verdict |",
        "|---|---|---|---|",
        _start_row("first run, new database", app_health.first),
        _start_row("median, new database", app_health.median),
        _start_row("median, database at head", head_app_health.median),
        _memory_row("backend (USS, median), new database", backend_idle, BACKEND_RSS_BUDGET_MB),
        _memory_row(
            "backend (USS, median), database at head", head_backend_idle, BACKEND_RSS_BUDGET_MB
        ),
        _memory_row("whole app (USS, median), new database", app_idle, APP_RSS_BUDGET_MB),
        _memory_row("whole app (USS, median), database at head", head_app_idle, APP_RSS_BUDGET_MB),
        f"| Bundle: backend onedir + shell exe (uncompressed) | {_mb(bundle_total)} MB "
        f"| installer < {INSTALLER_BUDGET_MB} MB (T-803) "
        f"| {verdict(_mb_value(bundle_total), INSTALLER_BUDGET_MB)} |",
        f"| Backend exits by itself when the shell is killed | {orphans} orphan(s) "
        f"in {len(report.orphan_checks)} runs | 0 | {'pass' if orphans == 0 else 'FAIL'} |",
        "",
        "Memory budgets are judged on USS (memory private to each process). RSS is shown for "
        "reference only: summed RSS counts the pages that WebView2 processes share several "
        "times, so it overstates what the app costs.",
        "",
        "## Bundle size",
        "",
        "| Part | Size | Files |",
        "|---|---|---|",
        f"| Backend onedir (PyInstaller, no UPX) | {_mb(report.backend_bundle_bytes)} MB "
        f"| {report.backend_bundle_files} |",
        f"| Desktop shell exe (release) | {_mb(report.shell_exe_bytes)} MB | 1 |",
        "",
        "## Cold start (seconds)",
        "",
        "| Measure | Database | First run | Median | Range |",
        "|---|---|---|---|---|",
        *(
            f"| {label} | {kind} | {_s(summarise(values))} |"
            for label, new_values, head_values in timings
            for kind, values in (("new", new_values), ("at head", head_values))
        ),
        "",
        "## Idle memory (MB)",
        "",
        "| Process | Database | Count | RSS | USS |",
        "|---|---|---|---|---|",
        *(
            f"| {label} | {kind} | {count} | {_mb(memory.rss)} | {_mb(memory.uss)} |"
            for label, count, new_memory, head_memory in memories
            for kind, memory in (("new", new_memory), ("at head", head_memory))
        ),
        "",
        "Whole-app breakdown, last run with a new database:",
        "",
        "| Process | Count | RSS | USS |",
        "|---|---|---|---|",
        *(
            f"| {name} | {count} | {_mb(mem.rss)} | {_mb(mem.uss)} |"
            for name, count, mem in group_by_name(last_run)
        ),
        "",
        "## Method and caveats",
        "",
        "- New database: each run starts from a fresh temporary data directory, so the backend "
        "creates and migrates the database (Alembic and SQLAlchemy are imported). Database at "
        "head: all runs share one temporary data directory, seeded by an untimed start and "
        "checked to be at the head revision, so the backend takes the fast path (ADR-040).",
        "- The backend alone is started as the shell starts it (`--port 0 --exit-on-stdin-eof`, "
        "token in `ASSISTANT_PROF_TOKEN`); the whole app is the release shell exe, which spawns "
        "the packaged backend itself. The whole-app runs come first, so the backend-alone runs "
        "are always warm.",
        '- "First run" is the closest this script gets to a cold start, but the OS file cache '
        "may already hold the files. A true cold start, after a reboot, is a manual check. "
        "Windows Defender also scans a new executable on its first launch, which inflates the "
        "first run after each build (it falls in the new-database series).",
        "- The cold-start budget is set for a 4-core 2015-era CPU; on a faster machine, compare "
        "with care. T-806 measures on low-end hardware.",
        "- Memory is sampled after the idle wait. Whole app = the shell process and all its "
        "descendants (WebView2 processes and the backend).",
        "- After each whole-app run, the shell is killed (as from the Task Manager) and the "
        "backend must exit by itself within "
        f"{EXIT_TIMEOUT_S:g} s, because its stdin pipe closes (ADR-038).",
        "- Repeated after LangGraph is added (T-402) against the ADR-029 gate.",
        "",
    ]
    return "\n".join(lines)


def _mb_value(value: int | None) -> float | None:
    return None if value is None else value / MB


# --- Measurement (I/O) ---------------------------------------------------------------------


def _read_line_with_timeout(stream: IO[str], timeout: float) -> str:
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        lines.put(stream.readline())
        for _ in stream:  # keep draining so the child never blocks on a full pipe
            pass

    threading.Thread(target=pump, daemon=True).start()
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty:
        raise MeasureError(f"no output line within {timeout:g} s") from None
    if not line:
        raise MeasureError("the process exited before writing its line")
    return line


def _health_ok(port: int, token: str) -> bool:
    request = urllib.request.Request(  # fixed http://127.0.0.1 URL
        f"http://127.0.0.1:{port}/health", headers={"X-Session-Token": token}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError):
        return False


def _memory(process: psutil.Process) -> ProcessMemory:
    try:
        info = process.memory_full_info()
        return ProcessMemory(process.name(), info.rss, info.uss)
    except psutil.AccessDenied:
        return ProcessMemory(process.name(), process.memory_info().rss, None)


def _tree_memory(root: psutil.Process) -> list[ProcessMemory]:
    samples = []
    for process in [root, *root.children(recursive=True)]:
        try:
            samples.append(_memory(process))
        except psutil.NoSuchProcess:
            continue
    return samples


def log_tail(data_dir: Path, lines: int = 15) -> str:
    """Last backend log lines of a run, appended to error messages (the log is redacted)."""
    log_file = data_dir / "logs" / "assistant-prof.log"
    try:
        tail = log_file.read_text(encoding="utf-8").splitlines()[-lines:]
    except OSError:
        return f"\n(no backend log at {log_file})"
    return "\nlast backend log lines:\n" + "\n".join(tail)


def _clean_env(data_dir: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ASSISTANT_PROF_")}
    env["ASSISTANT_PROF_DATA_DIR"] = str(data_dir)
    return env


@contextmanager
def _data_dir(shared: Path | None) -> Iterator[Path]:
    """Yield ``shared`` (database at head) or a fresh temporary directory (new database)."""
    if shared is not None:
        yield shared
        return
    with tempfile.TemporaryDirectory(prefix="ap-measure-") as fresh:
        yield Path(fresh)


def check_at_head(data_dir: Path) -> None:
    """Raise ``MeasureError`` unless the data directory's database is at the head revision."""
    database = DataPaths(data_dir).database
    try:
        revision = read_revision(database)
    except sqlite3.Error as exc:
        raise MeasureError(f"cannot read {database}: {exc}") from exc
    if revision != HEAD_REVISION:
        raise MeasureError(
            f"seeded database is at revision {revision!r}, expected {HEAD_REVISION!r}"
        )


def measure_backend(
    exe: Path, idle_seconds: float, samples: BackendSamples, shared_dir: Path | None = None
) -> None:
    """One run of the packaged backend alone, in ``shared_dir`` or a fresh data directory."""
    token = secrets.token_hex(32)
    with _data_dir(shared_dir) as data_dir:
        env = _clean_env(Path(data_dir))
        env["ASSISTANT_PROF_TOKEN"] = token
        started = time.perf_counter()
        process = subprocess.Popen(  # noqa: S603  # our own executable, fixed arguments
            [str(exe), "--port", "0", "--exit-on-stdin-eof"],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            if process.stdout is None or process.stdin is None:
                raise MeasureError("backend pipes are missing")
            line = _read_line_with_timeout(process.stdout, STARTUP_TIMEOUT_S)
            ready_at = time.perf_counter()
            port = int(json.loads(line)["port"])
            while not _health_ok(port, token):
                if time.perf_counter() - started > STARTUP_TIMEOUT_S:
                    raise MeasureError("backend never answered /health with 200")
                time.sleep(HEALTH_POLL_S)
            healthy_at = time.perf_counter()
            time.sleep(idle_seconds)
            samples.memory.append(_memory(psutil.Process(process.pid)))
            samples.ready_s.append(ready_at - started)
            samples.health_s.append(healthy_at - started)
            process.stdin.close()
            try:
                code = process.wait(timeout=EXIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                raise MeasureError(
                    f"backend still running {EXIT_TIMEOUT_S:g} s after its stdin was closed"
                    + log_tail(Path(data_dir))
                ) from None
            if code != 0:
                raise MeasureError(f"backend exited with code {code}" + log_tail(Path(data_dir)))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def measure_app(
    app_exe: Path,
    backend_exe: Path,
    idle_seconds: float,
    report: Report,
    shared_dir: Path | None = None,
) -> None:
    """One run of the whole app: the shell spawns the backend and reports its health."""
    samples = report.app_new_db if shared_dir is None else report.app_at_head
    with _data_dir(shared_dir) as data_dir:
        env = _clean_env(Path(data_dir))
        env["ASSISTANT_PROF_BACKEND_EXE"] = str(backend_exe)
        started = time.perf_counter()
        shell = subprocess.Popen(  # noqa: S603  # our own executable
            [str(app_exe)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        root = psutil.Process(shell.pid)
        tree: list[psutil.Process] = []
        try:
            if shell.stdout is None:
                raise MeasureError("shell stdout pipe is missing")
            event = parse_shell_event(_read_line_with_timeout(shell.stdout, STARTUP_TIMEOUT_S))
            healthy_at = time.perf_counter()
            if event.event != "backend_healthy" or event.backend_pid is None:
                raise MeasureError(f"the shell could not start the backend: {event.error}")
            time.sleep(idle_seconds)
            tree = root.children(recursive=True)
            samples.memory.append(_tree_memory(root))
            samples.health_s.append(healthy_at - started)
            samples.shell_reported_s.append((event.elapsed_ms or 0) / 1000)
            backend = psutil.Process(event.backend_pid)
            shell.kill()  # like the Task Manager: no graceful shutdown from the shell
            shell.wait()
            exited = _exits_within(backend, EXIT_TIMEOUT_S)
            report.orphan_checks.append(exited)
            if not exited:
                note = "backend still running after the shell was killed"
                sys.stderr.write(f"measure: {note}{log_tail(Path(data_dir))}\n")
        finally:
            if shell.poll() is None:
                shell.kill()
                shell.wait()
            _kill_all(tree)


def _exits_within(process: psutil.Process, timeout: float) -> bool:
    try:
        process.wait(timeout=timeout)
    except psutil.TimeoutExpired:
        return False
    return True


def _kill_all(processes: Sequence[psutil.Process]) -> None:
    for process in processes:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            continue


def _cpu_name() -> str:
    if os.name == "nt":
        # Imported by name: a sys.platform check would make mypy flag one branch on each OS.
        winreg = importlib.import_module("winreg")
        key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            return str(winreg.QueryValueEx(handle, "ProcessorNameString")[0]).strip()
    return platform.processor() or platform.machine()


def _commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(  # noqa: S603  # fixed git command
            ["git", *args],  # noqa: S607  # git from PATH
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    try:
        dirty = "-dirty" if git("status", "--porcelain") else ""
        return git("rev-parse", "--short", "HEAD") + dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def machine() -> Machine:
    """Describe the machine running the measurement."""
    return Machine(
        cpu=_cpu_name(),
        cores=psutil.cpu_count(logical=False),
        threads=psutil.cpu_count(logical=True),
        ram_bytes=psutil.virtual_memory().total,
        os=platform.platform(),
        python=platform.python_version(),
        commit=_commit(),
    )


@contextmanager
def _seeded_dir(backend_exe: Path, progress: Callable[[str], None]) -> Iterator[Path]:
    """Yield a temporary data directory whose database an untimed start brought to head."""
    with tempfile.TemporaryDirectory(prefix="ap-measure-head-") as shared:
        progress("seeding a database at head (untimed)")
        measure_backend(backend_exe, 0, BackendSamples(), Path(shared))
        check_at_head(Path(shared))
        yield Path(shared)


def run(
    args: argparse.Namespace,
    *,
    today: date,
    progress: Callable[[str], None],
) -> Path:
    """Run every measurement and write the report; return its path."""
    backend_exe: Path = args.backend_exe.resolve()
    app_exe: Path = args.app_exe.resolve()
    for exe in (backend_exe, app_exe):
        if not exe.is_file():
            raise MeasureError(f"not found: {exe} (run `just measure`, which builds it)")
    bundle_bytes, bundle_files = dir_size(backend_exe.parent)
    report = Report(
        machine=machine(),
        runs=args.runs,
        idle_seconds=args.idle_seconds,
        backend_bundle_bytes=bundle_bytes,
        backend_bundle_files=bundle_files,
        shell_exe_bytes=app_exe.stat().st_size,
    )
    # Whole app first: its first run, the budgeted one, then includes the first launch of a
    # fresh build (antivirus scan, cold file cache) instead of the backend-alone runs.
    for index in range(1, args.runs + 1):
        progress(f"whole app, new database, run {index}/{args.runs}")
        measure_app(app_exe, backend_exe, args.idle_seconds, report)
    with _seeded_dir(backend_exe, progress) as shared:
        for index in range(1, args.runs + 1):
            progress(f"whole app, database at head, run {index}/{args.runs}")
            measure_app(app_exe, backend_exe, args.idle_seconds, report, shared)
    for index in range(1, args.runs + 1):
        progress(f"backend alone, new database, run {index}/{args.runs}")
        measure_backend(backend_exe, args.idle_seconds, report.backend_new_db)
    with _seeded_dir(backend_exe, progress) as shared:
        for index in range(1, args.runs + 1):
            progress(f"backend alone, database at head, run {index}/{args.runs}")
            measure_backend(backend_exe, args.idle_seconds, report.backend_at_head, shared)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today.isoformat()}-{args.name}.md"
    path.write_text(render_report(report, today), encoding="utf-8", newline="\n")
    return path


def build_parser() -> argparse.ArgumentParser:
    """Command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--backend-exe", type=Path, required=True)
    parser.add_argument("--app-exe", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--name", default="walking-skeleton", help="report name suffix")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--idle-seconds", type=float, default=10.0)
    return parser


def main(argv: Sequence[str]) -> int:
    """Entry point; returns 1 if a run broke the startup contract."""
    args = build_parser().parse_args(argv)

    def progress(message: str) -> None:
        sys.stderr.write(f"measure: {message}\n")

    try:
        path = run(args, today=date.today(), progress=progress)  # local date
    except MeasureError as exc:
        sys.stderr.write(f"measure: failed: {exc}\n")
        return 1
    if isinstance(sys.stdout, io.TextIOWrapper):  # a Windows console may not encode "→" or "§"
        sys.stdout.reconfigure(errors="replace")
    sys.stdout.write(path.read_text(encoding="utf-8"))
    sys.stdout.write(f"\nReport written to {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
