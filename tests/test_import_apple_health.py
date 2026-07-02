"""Tests for Apple Health import helpers."""
from __future__ import annotations

from medbots.import_apple_health import (
    DailyAgg,
    build_body_metrics,
    is_valid_day,
    normalize_body_fat,
    parse_apple_datetime,
)


def test_parse_apple_datetime_with_timezone() -> None:
    dt = parse_apple_datetime("2024-06-01 12:30:00 +0300")
    assert dt.year == 2024
    assert dt.month == 6
    assert dt.day == 1


def test_normalize_body_fat_fraction() -> None:
    assert normalize_body_fat(0.245, "") == 24.5


def test_build_body_metrics_minimal_day() -> None:
    daily = {
        "2024-06-01": DailyAgg(steps=8000, sleep_seconds=7 * 3600, hr_resting_sum=60, hr_resting_n=1),
    }
    entries = build_body_metrics(daily)
    assert len(entries) == 1
    assert entries[0]["date"] == "2024-06-01"
    assert entries[0]["steps"] == 8000
    assert entries[0]["source"] == "apple_health"


def test_is_valid_day_filters_apple_epoch() -> None:
    assert is_valid_day("2015-01-01") is True
    assert is_valid_day("1970-01-01") is False
