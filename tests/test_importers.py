"""Tests for schedule importers."""

from __future__ import annotations

import pytest

from gridguard.importers import load_any, schedule_from_csv
from gridguard.schedule import ScheduleError

_CSV = """type,days,date,start,end,reason
recurring,daily,,02:00,04:00,scheduled load-shedding
recurring,mon|wed|fri,,20:00,22:00,peak-hour shedding
oneoff,,2026-06-15,09:00,13:00,grid maintenance
"""


def test_csv_to_schedule():
    s = schedule_from_csv(_CSV, zone="Z1")
    assert s.zone == "Z1"
    assert len(s.recurring) == 2
    assert len(s.one_off) == 1
    assert s.one_off[0].reason == "grid maintenance"
    assert s.recurring[1].days == (0, 2, 4)


def test_csv_missing_required_column_raises():
    bad = "days,start\nmon,10:00\n"  # no 'type', no 'end'
    with pytest.raises(ScheduleError):
        schedule_from_csv(bad, zone="Z")


def test_csv_recurring_without_days_raises():
    bad = "type,days,date,start,end\nrecurring,,,10:00,11:00\n"
    with pytest.raises(ScheduleError):
        schedule_from_csv(bad, zone="Z")


def test_csv_oneoff_without_date_raises():
    bad = "type,days,date,start,end\noneoff,,,10:00,11:00\n"
    with pytest.raises(ScheduleError):
        schedule_from_csv(bad, zone="Z")


def test_csv_unknown_type_raises():
    bad = "type,days,date,start,end\nweird,daily,,10:00,11:00\n"
    with pytest.raises(ScheduleError):
        schedule_from_csv(bad, zone="Z")


def test_csv_blank_lines_skipped():
    text = _CSV + "\n\n"
    s = schedule_from_csv(text, zone="Z")
    assert len(s.recurring) == 2


def test_csv_round_trips_through_json():
    s = schedule_from_csv(_CSV, zone="Z1")
    again = type(s).from_json(s.to_json())
    assert len(again.recurring) == len(s.recurring)
    assert len(again.one_off) == len(s.one_off)


def test_load_any_csv(tmp_path):
    p = tmp_path / "sched.csv"
    p.write_text(_CSV, encoding="utf-8")
    s = load_any(p, zone="Z9")
    assert s.zone == "Z9"


def test_load_any_csv_requires_zone(tmp_path):
    p = tmp_path / "sched.csv"
    p.write_text(_CSV, encoding="utf-8")
    with pytest.raises(ScheduleError):
        load_any(p)  # no zone


def test_load_any_json(tmp_path):
    p = tmp_path / "sched.json"
    p.write_text(
        '{"version":1,"zone":"J","timezone":"Asia/Karachi",'
        '"recurring":[{"days":"daily","start":"01:00","end":"02:00"}]}',
        encoding="utf-8",
    )
    s = load_any(p)
    assert s.zone == "J"
