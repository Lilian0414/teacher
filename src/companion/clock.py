from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from companion.settings import get_settings

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(tz=ZoneInfo(get_settings().timezone))
