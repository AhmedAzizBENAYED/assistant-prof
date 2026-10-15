"""Injectable time source, so time-dependent logic is testable."""

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Source of wall-clock and monotonic time."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        ...

    def monotonic(self) -> float:
        """Return seconds from an arbitrary origin, never going backwards."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        return datetime.now(UTC)

    def monotonic(self) -> float:
        """Return :func:`time.perf_counter` (finer than ``time.monotonic`` on Windows)."""
        return time.perf_counter()


class FakeClock:
    """Manually driven clock for tests."""

    def __init__(self, start: datetime | None = None) -> None:
        if start is not None and start.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = start if start is not None else datetime(2026, 1, 1, tzinfo=UTC)
        self._monotonic = 0.0

    def now(self) -> datetime:
        """Return the current fake time."""
        return self._now

    def monotonic(self) -> float:
        """Return the fake monotonic time."""
        return self._monotonic

    def advance(self, seconds: float) -> None:
        """Move both clocks forward."""
        if seconds < 0:
            raise ValueError("time cannot go backwards")
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds
