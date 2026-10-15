import uuid
from datetime import UTC, datetime, timedelta

import pytest

from assistant_prof.core.clock import FakeClock, SystemClock
from assistant_prof.core.ids import is_valid_correlation_id, new_correlation_id, new_uuid


def test_new_uuid_is_a_unique_uuid4() -> None:
    first, second = new_uuid(), new_uuid()
    assert uuid.UUID(first).version == 4
    assert first != second


def test_new_correlation_id_is_valid() -> None:
    assert is_valid_correlation_id(new_correlation_id())


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("abcd1234", True),
        ("req-42.retry_1", True),
        ("a" * 64, True),
        ("short", False),
        ("a" * 65, False),
        ("has space-123", False),
        ("line\nbreak123", False),
        ('quote"injection', False),
    ],
)
def test_correlation_id_validation(value: str, valid: bool) -> None:
    assert is_valid_correlation_id(value) is valid


def test_system_clock_is_aware_and_monotonic() -> None:
    clock = SystemClock()
    assert clock.now().tzinfo is UTC
    first = clock.monotonic()
    assert clock.monotonic() >= first


def test_fake_clock_advances_both_clocks() -> None:
    start = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    clock = FakeClock(start)
    clock.advance(90)
    assert clock.now() == start + timedelta(seconds=90)
    assert clock.monotonic() == 90


def test_fake_clock_rejects_naive_start_and_negative_steps() -> None:
    with pytest.raises(ValueError, match="aware"):
        FakeClock(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="backwards"):
        FakeClock().advance(-1)
