import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "measure.py"
MB = 1024 * 1024


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure"] = module  # dataclasses look their module up while being created
    spec.loader.exec_module(module)
    return module


measure = load_script()


def test_parse_shell_events() -> None:
    healthy = measure.parse_shell_event(
        '{"event":"backend_healthy","elapsed_ms":812,"port":5000,"backend_pid":42,'
        '"version":"0.1.0"}\n'
    )
    assert healthy.event == "backend_healthy"
    assert healthy.elapsed_ms == 812
    assert healthy.backend_pid == 42
    failed = measure.parse_shell_event('{"event":"backend_failed","error":"no ready line"}')
    assert failed.error == "no ready line"


@pytest.mark.parametrize("line", ["", "not json", '{"event":"other"}', "[]"])
def test_parse_shell_event_rejects_other_lines(line: str) -> None:
    with pytest.raises(measure.MeasureError):
        measure.parse_shell_event(line)


def test_summarise_keeps_first_run_apart() -> None:
    stat = measure.summarise([3.0, 1.0, 2.0, 1.5])
    assert stat.first == 3.0
    assert stat.median == 1.75
    assert (stat.minimum, stat.maximum) == (1.0, 3.0)
    with pytest.raises(ValueError, match="no values"):
        measure.summarise([])


def test_total_never_under_reports_unknown_uss() -> None:
    known = [measure.ProcessMemory("a", 10, 4), measure.ProcessMemory("b", 20, 6)]
    assert measure.total(known) == measure.MemoryTotal(rss=30, uss=10)
    partial = [*known, measure.ProcessMemory("c", 5, None)]
    assert measure.total(partial) == measure.MemoryTotal(rss=35, uss=None)


def test_group_by_name_sums_and_sorts_by_uss() -> None:
    processes = [
        measure.ProcessMemory("msedgewebview2.exe", 100, 30),
        measure.ProcessMemory("assistant-prof-backend.exe", 60, 50),
        measure.ProcessMemory("msedgewebview2.exe", 80, 25),
    ]
    groups = measure.group_by_name(processes)
    assert [(name, count) for name, count, _ in groups] == [
        ("msedgewebview2.exe", 2),
        ("assistant-prof-backend.exe", 1),
    ]
    assert groups[0][2] == measure.MemoryTotal(rss=180, uss=55)


def test_verdict() -> None:
    assert measure.verdict(1.0, 2.0) == "pass"
    assert measure.verdict(2.0, 2.0) == "FAIL"
    assert measure.verdict(None, 2.0) == "n/a"


def test_dir_size(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bin").write_bytes(b"x" * 10)
    (tmp_path / "sub" / "b.bin").write_bytes(b"y" * 5)
    assert measure.dir_size(tmp_path) == (15, 2)


def _report() -> object:
    machine = measure.Machine(
        cpu="Test CPU",
        cores=4,
        threads=8,
        ram_bytes=8 * 1024 * MB,
        os="TestOS",
        python="3.12.0",
        commit="abc1234",
    )
    backend = measure.ProcessMemory("assistant-prof-backend.exe", 60 * MB, 40 * MB)
    app_run = [
        measure.ProcessMemory("assistant-prof.exe", 30 * MB, 10 * MB),
        measure.ProcessMemory("msedgewebview2.exe", 300 * MB, 200 * MB),
        backend,
    ]
    return measure.Report(
        machine=machine,
        runs=2,
        idle_seconds=5,
        backend_bundle_bytes=37 * MB,
        backend_bundle_files=300,
        shell_exe_bytes=10 * MB,
        backend_ready_s=[1.2, 0.6],
        backend_health_s=[1.3, 0.7],
        backend_memory=[backend, backend],
        app_health_s=[2.5, 1.5],
        app_shell_reported_s=[2.4, 1.4],
        app_memory=[app_run, app_run],
        orphan_checks=[True, True],
    )


def test_render_report_judges_budgets_on_uss() -> None:
    text = measure.render_report(_report(), date(2026, 10, 15))
    assert text.startswith("# Walking-skeleton measurement, 2026-10-15")
    assert "| Cold start, whole app, first run | 2.50 s | < 6 s | pass |" in text
    assert "| Idle memory, backend (USS, median) | 40.0 MB | < 250 MB | pass |" in text
    # USS total 250 MB passes although summed RSS (390 MB) would be the larger figure.
    assert "| Idle memory, whole app (USS, median) | 250.0 MB | < 450 MB | pass |" in text
    assert "| msedgewebview2.exe | 1 | 300.0 | 200.0 |" in text
    assert "0 orphan(s) in 2 runs | 0 | pass |" in text
    assert "manual check" in text
    assert "Windows Defender" in text


def test_render_report_flags_failures() -> None:
    report = _report()
    report.app_health_s = [7.0, 6.5]  # type: ignore[attr-defined]
    report.orphan_checks = [True, False]  # type: ignore[attr-defined]
    text = measure.render_report(report, date(2026, 10, 15))
    assert "| Cold start, whole app, median | 6.75 s | < 6 s | FAIL |" in text
    assert "1 orphan(s) in 2 runs | 0 | FAIL |" in text


def test_main_reports_missing_executables(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = measure.main(
        [
            "--backend-exe",
            str(tmp_path / "missing-backend.exe"),
            "--app-exe",
            str(tmp_path / "missing-app.exe"),
            "--out-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 1
    assert "not found" in capsys.readouterr().err
    assert not (tmp_path / "reports").exists()


def test_log_tail(tmp_path: Path) -> None:
    assert "no backend log" in measure.log_tail(tmp_path)
    (tmp_path / "logs").mkdir()
    lines = [f'{{"event":"e{i}"}}' for i in range(20)]
    (tmp_path / "logs" / "assistant-prof.log").write_text("\n".join(lines), encoding="utf-8")
    tail = measure.log_tail(tmp_path, lines=3)
    assert tail.endswith('{"event":"e17"}\n{"event":"e18"}\n{"event":"e19"}')
    assert '"e16"' not in tail
