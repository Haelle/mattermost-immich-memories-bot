from datetime import datetime, time

import pytest

from souvenirs.schedule import is_due, next_tick


@pytest.mark.parametrize(
    ("send_time", "tick", "interval", "expected"),
    [
        (time(8, 30), time(9, 0), 60, True),
        (time(9, 0), time(9, 0), 60, True),
        (time(8, 0), time(9, 0), 60, False),
        (time(9, 15), time(9, 0), 60, False),
        (time(9, 0), time(9, 0), 1, True),
        (time(8, 59), time(9, 0), 1, False),
        (time(9, 10), time(9, 15), 15, True),
        (time(9, 0), time(9, 15), 15, False),
        (time(23, 30), time(0, 0), 60, True),
        (time(0, 0), time(0, 0), 60, True),
        (time(0, 30), time(0, 0), 60, False),
    ],
)
def test_user_is_due_when_send_time_falls_in_the_elapsed_window(send_time, tick, interval, expected):
    assert is_due(send_time, tick, interval) is expected


@pytest.mark.parametrize(
    ("now", "interval", "expected"),
    [
        (datetime(2026, 10, 11, 9, 47, 12), 60, datetime(2026, 10, 11, 10, 0)),
        (datetime(2026, 10, 11, 9, 47, 12), 15, datetime(2026, 10, 11, 10, 0)),
        (datetime(2026, 10, 11, 9, 30, 0), 15, datetime(2026, 10, 11, 9, 45)),
        (datetime(2026, 10, 11, 9, 47, 12), 1, datetime(2026, 10, 11, 9, 48)),
        (datetime(2026, 10, 11, 23, 50), 15, datetime(2026, 10, 12, 0, 0)),
    ],
)
def test_next_tick_is_the_next_interval_boundary_since_midnight(now, interval, expected):
    assert next_tick(now, interval) == expected
