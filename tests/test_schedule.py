"""Tests for the Schedule model."""

from __future__ import annotations

from datetime import date

import pytest

from gridguard.schedule import OutageWindow, Schedule, ScheduleError
from tests.conftest import KHI, dt


def test_parse_days_daily_and_named():
    s = Schedule.from_dict(
        {
            "version": 1,
            "zone": "Z",
            "timezone": "Asia/Karachi",
            "recurring": [
                {"days": "daily", "start": "01:00", "end": "02:00"},
                {"days": "mon|wed|fri", "start": "03:00", "end": "04:00"},
            ],
        }
    )
    assert s.recurring[0].days == (0, 1, 2, 3, 4, 5, 6)
    assert s.recurring[1].days == (0, 2, 4)


def test_invalid_day_raises():
    with pytest.raises(ScheduleError):
        Schedule.from_dict(
            {
                "version": 1,
                "zone": "Z",
                "recurring": [{"days": "funday", "start": "1:00", "end": "2:00"}],
            }
        )


def test_invalid_time_raises():
    with pytest.raises(ScheduleError):
        Schedule.from_dict(
            {
                "version": 1,
                "zone": "Z",
                "recurring": [{"days": "daily", "start": "25:99", "end": "2:00"}],
            }
        )


def test_missing_zone_raises():
    with pytest.raises(ScheduleError):
        Schedule.from_dict({"version": 1, "recurring": []})


def test_bad_version_raises():
    with pytest.raises(ScheduleError):
        Schedule.from_dict({"version": 99, "zone": "Z"})


def test_outage_window_invariant():
    with pytest.raises(ScheduleError):
        OutageWindow(dt(2026, 6, 16, 16), dt(2026, 6, 16, 14))


def test_expand_basic_window(simple_schedule):
    wins = simple_schedule.expand(date(2026, 6, 16), date(2026, 6, 16))
    afternoons = [w for w in wins if w.reason == "afternoon"]
    assert len(afternoons) == 1
    w = afternoons[0]
    assert w.start == dt(2026, 6, 16, 14)
    assert w.end == dt(2026, 6, 16, 16)


def test_expand_crosses_midnight(simple_schedule):
    wins = simple_schedule.expand(date(2026, 6, 16), date(2026, 6, 16))
    nights = [w for w in wins if w.reason == "night"]
    assert len(nights) == 1
    n = nights[0]
    assert n.start == dt(2026, 6, 16, 22)
    assert n.end == dt(2026, 6, 17, 0)  # rolls to next day


def test_expand_includes_genuinely_crossing_previous_day_window():
    # A 23:00-02:00 cut starting Tue night must appear when querying Wednesday.
    s = Schedule.from_dict(
        {
            "version": 1,
            "zone": "Z",
            "recurring": [{"days": "daily", "start": "23:00", "end": "02:00"}],
        }
    )
    wins = s.expand(date(2026, 6, 17), date(2026, 6, 17))
    starts = {w.start for w in wins}
    assert dt(2026, 6, 16, 23) in starts  # began previous evening


def test_expand_excludes_stale_previous_day_window(simple_schedule):
    # The 16th's 14:00-16:00 cut must NOT leak into a query for the 17th,
    # and a 22:00-00:00 window ending exactly at midnight doesn't overlap
    # the next day either (half-open windows).
    wins = simple_schedule.expand(date(2026, 6, 17), date(2026, 6, 17))
    assert dt(2026, 6, 16, 14) not in {w.start for w in wins}
    assert all(w.end > dt(2026, 6, 17, 0) for w in wins)


def test_one_off_only_on_its_date(simple_schedule):
    on_day = simple_schedule.expand(date(2026, 6, 20), date(2026, 6, 20))
    assert any(w.reason == "maintenance" for w in on_day)
    other_day = simple_schedule.expand(date(2026, 6, 21), date(2026, 6, 21))
    assert not any(w.reason == "maintenance" for w in other_day)


def test_weekday_filtering():
    # Cut only on Mondays. 2026-06-15 is a Monday, 2026-06-16 a Tuesday.
    s = Schedule.from_dict(
        {
            "version": 1,
            "zone": "Z",
            "recurring": [{"days": "mon", "start": "10:00", "end": "11:00"}],
        }
    )
    mon = s.expand(date(2026, 6, 15), date(2026, 6, 15))
    tue = s.expand(date(2026, 6, 16), date(2026, 6, 16))
    assert len(mon) == 1
    assert len(tue) == 0


def test_merge_overlapping_windows():
    s = Schedule.from_dict(
        {
            "version": 1,
            "zone": "Z",
            "recurring": [
                {"days": "daily", "start": "10:00", "end": "12:00"},
                {"days": "daily", "start": "11:00", "end": "13:00"},
            ],
        }
    )
    merged = s.merged(date(2026, 6, 16), date(2026, 6, 16))
    same_day = [w for w in merged if w.start.date() == date(2026, 6, 16)]
    assert len(same_day) == 1
    assert same_day[0].start == dt(2026, 6, 16, 10)
    assert same_day[0].end == dt(2026, 6, 16, 13)


def test_merge_adjacent_windows():
    s = Schedule.from_dict(
        {
            "version": 1,
            "zone": "Z",
            "recurring": [
                {"days": "daily", "start": "10:00", "end": "12:00"},
                {"days": "daily", "start": "12:00", "end": "14:00"},
            ],
        }
    )
    merged = s.merged(date(2026, 6, 16), date(2026, 6, 16))
    same_day = [w for w in merged if w.start.date() == date(2026, 6, 16)]
    assert len(same_day) == 1
    assert same_day[0].end == dt(2026, 6, 16, 14)


def test_json_round_trip(simple_schedule):
    text = simple_schedule.to_json()
    again = Schedule.from_json(text)
    assert again.zone == simple_schedule.zone
    assert len(again.recurring) == len(simple_schedule.recurring)
    assert len(again.one_off) == len(simple_schedule.one_off)


def test_tz_is_zoneinfo(simple_schedule):
    assert simple_schedule.tz == KHI
