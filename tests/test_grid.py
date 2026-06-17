"""Tests for the grid oracle."""

from __future__ import annotations

from datetime import timedelta

from gridguard.grid import GridOracle
from gridguard.schedule import Schedule
from tests.conftest import dt


def test_is_off_inside_window(simple_schedule):
    o = GridOracle(simple_schedule)
    assert o.is_off(dt(2026, 6, 16, 15))  # 15:00 in 14-16 cut
    assert not o.is_off(dt(2026, 6, 16, 13))  # 13:00 powered


def test_window_is_half_open(simple_schedule):
    o = GridOracle(simple_schedule)
    # cut is [14:00, 16:00) -> 16:00 itself is powered again
    assert not o.is_off(dt(2026, 6, 16, 16))
    assert o.is_off(dt(2026, 6, 16, 14))


def test_runway_when_powered(simple_schedule):
    o = GridOracle(simple_schedule)
    assert o.runway(dt(2026, 6, 16, 12)) == timedelta(hours=2)  # cut at 14:00
    assert o.runway(dt(2026, 6, 16, 16, 30)) == timedelta(
        hours=5, minutes=30
    )  # cut at 22


def test_runway_zero_when_off(simple_schedule):
    o = GridOracle(simple_schedule)
    assert o.runway(dt(2026, 6, 16, 15)) == timedelta(0)


def test_runway_none_when_no_cut():
    # An empty schedule has no cuts at all -> unlimited runway.
    s = Schedule.from_dict({"version": 1, "zone": "Z", "recurring": []})
    o = GridOracle(s)
    assert o.runway(dt(2026, 6, 16, 12)) is None


def test_next_window_after(simple_schedule):
    o = GridOracle(simple_schedule)
    nxt = o.next_window_after(dt(2026, 6, 16, 12))
    assert nxt is not None
    assert nxt.start == dt(2026, 6, 16, 14)


def test_current_window(simple_schedule):
    o = GridOracle(simple_schedule)
    cur = o.current_window(dt(2026, 6, 16, 15))
    assert cur is not None and cur.reason == "afternoon"
    assert o.current_window(dt(2026, 6, 16, 12)) is None


def test_safe_start_now_when_enough_runway(simple_schedule):
    o = GridOracle(simple_schedule)
    now = dt(2026, 6, 16, 12)  # 2h runway
    assert o.next_safe_start(now, timedelta(hours=2)) == now


def test_safe_start_jumps_past_cut(simple_schedule):
    o = GridOracle(simple_schedule)
    now = dt(2026, 6, 16, 13)  # only 1h runway before 14:00 cut
    safe = o.next_safe_start(now, timedelta(minutes=90))
    assert safe == dt(2026, 6, 16, 16)  # right after the afternoon cut ends


def test_safe_start_when_off_now(simple_schedule):
    o = GridOracle(simple_schedule)
    now = dt(2026, 6, 16, 15)  # power is out
    safe = o.next_safe_start(now, timedelta(minutes=30))
    assert safe == dt(2026, 6, 16, 16)  # power returns at 16:00 with 6h runway


def test_safe_start_needs_long_window(simple_schedule):
    o = GridOracle(simple_schedule)
    now = dt(2026, 6, 16, 16, 30)  # 5.5h until 22:00 cut
    # needs 10h -> must wait until the night cut ends (next day 00:00),
    # which then has 14h until the next afternoon cut.
    safe = o.next_safe_start(now, timedelta(hours=10))
    assert safe == dt(2026, 6, 17, 0)


def test_horizon_validation():
    s = Schedule.from_dict({"version": 1, "zone": "Z", "recurring": []})
    try:
        GridOracle(s, horizon_days=0)
        assert False, "should have raised"
    except ValueError:
        pass
