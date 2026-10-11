import re
from datetime import datetime, time, timedelta

MINUTES_PER_DAY = 24 * 60
TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


def _minute_of_day(moment: time) -> int:
    return moment.hour * 60 + moment.minute


def is_due(send_time: time, tick: time, interval_minutes: int) -> bool:
    minutes_since_send_time = (_minute_of_day(tick) - _minute_of_day(send_time)) % MINUTES_PER_DAY
    return minutes_since_send_time < interval_minutes


def next_tick(now: datetime, interval_minutes: int) -> datetime:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_intervals = int((now - midnight) / timedelta(minutes=interval_minutes))
    return midnight + timedelta(minutes=interval_minutes * (elapsed_intervals + 1))


def parse_time(value: str) -> time | None:
    match = TIME_PATTERN.match(value)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2])
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)
