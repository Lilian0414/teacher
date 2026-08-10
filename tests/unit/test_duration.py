from datetime import timedelta

import pytest

from companion.commands.duration import parse_duration


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("15m", timedelta(minutes=15)),
        ("2h", timedelta(hours=2)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        (" 1M ", timedelta(minutes=1)),
    ],
)
def test_parse_duration(raw: str, expected: timedelta) -> None:
    assert parse_duration(raw) == expected


@pytest.mark.parametrize("raw", ["0m", "m", "10", "1d", "-1m", "1h0m", "0h30m"])
def test_parse_duration_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(raw)


def test_parse_duration_rejects_values_over_maximum() -> None:
    with pytest.raises(ValueError, match="maximum"):
        parse_duration("25h", max_duration=timedelta(hours=24))
