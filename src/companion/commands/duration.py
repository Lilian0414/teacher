import re
from datetime import timedelta

_DURATION_RE = re.compile(
    r"^(?:(?P<hours>[1-9]\d*)h)?(?:(?P<minutes>[1-9]\d*)m)?$"
)


def parse_duration(raw: str, *, max_duration: timedelta = timedelta(hours=24)) -> timedelta:
    text = raw.strip().lower()
    match = _DURATION_RE.fullmatch(text)
    if match is None or not match.group(0):
        raise ValueError("duration must look like 10m, 2h or 1h30m")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    duration = timedelta(hours=hours, minutes=minutes)
    if duration <= timedelta(0):
        raise ValueError("duration must be greater than zero")
    if duration > max_duration:
        raise ValueError("duration exceeds the configured maximum")
    return duration
