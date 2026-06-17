"""Tests for the guard decision logic and runner."""

from __future__ import annotations

from datetime import timedelta

from gridguard.duration import DurationOracle
from gridguard.exit_codes import ExitCode
from gridguard.grid import GridOracle
from gridguard.history import HistoryStore
from gridguard.runner import guard_run, plan_guard
from tests.conftest import dt


class FakeClock:
    """Returns queued datetimes; repeats the last one once exhausted."""

    def __init__(self, *moments):
        self._moments = list(moments)
        self._last = moments[-1]

    def __call__(self):
        if self._moments:
            self._last = self._moments.pop(0)
        return self._last


def _oracle(simple_schedule):
    return GridOracle(simple_schedule)


def _duration(fallback=120.0):
    return DurationOracle(HistoryStore(":memory:"), fallback_seconds=fallback)


# --- pure plan_guard --------------------------------------------------------
def test_plan_go_when_runway_sufficient(simple_schedule):
    o = _oracle(simple_schedule)
    plan = plan_guard(dt(2026, 6, 16, 12), o, timedelta(hours=1))
    assert plan.action == "go"


def test_plan_blocked_runway(simple_schedule):
    o = _oracle(simple_schedule)
    plan = plan_guard(dt(2026, 6, 16, 13), o, timedelta(minutes=90))
    assert plan.action == "blocked-runway"
    assert plan.safe_start == dt(2026, 6, 16, 16)


def test_plan_blocked_power_off(simple_schedule):
    o = _oracle(simple_schedule)
    plan = plan_guard(dt(2026, 6, 16, 15), o, timedelta(minutes=10))
    assert plan.action == "blocked-power-off"
    assert plan.current_outage.end == dt(2026, 6, 16, 16)
    assert plan.safe_start == dt(2026, 6, 16, 16)


# --- guard_run: dry-run -----------------------------------------------------
def test_dry_run_go_does_not_execute(simple_schedule):
    calls = []
    outcome = guard_run(
        ["docker", "build", "."],
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        history=HistoryStore(":memory:"),
        tz=simple_schedule.tz,
        safety_factor=1.0,
        estimate_override=3600,  # 1h
        dry_run=True,
        now_fn=lambda: dt(2026, 6, 16, 12),  # 2h runway
        runner=lambda argv: calls.append(argv) or 0,
    )
    assert outcome.action == "would-run"
    assert outcome.exit_code == int(ExitCode.OK)
    assert calls == []  # never ran


# --- guard_run: blocked -----------------------------------------------------
def test_blocked_returns_87(simple_schedule):
    outcome = guard_run(
        ["docker", "build", "."],
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        history=HistoryStore(":memory:"),
        tz=simple_schedule.tz,
        safety_factor=1.25,
        estimate_override=3600,  # 1h * 1.25 = 75min > 60min runway at 13:00
        now_fn=lambda: dt(2026, 6, 16, 13),
    )
    assert outcome.action == "blocked"
    assert outcome.exit_code == 87


def test_safety_factor_changes_decision(simple_schedule):
    common = dict(
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        tz=simple_schedule.tz,
        estimate_override=3600,  # 1h
        dry_run=True,
        now_fn=lambda: dt(2026, 6, 16, 13),  # exactly 1h runway
    )
    ok = guard_run(["x"], history=HistoryStore(":memory:"), safety_factor=1.0, **common)
    blocked = guard_run(
        ["x"], history=HistoryStore(":memory:"), safety_factor=2.0, **common
    )
    assert ok.action == "would-run"
    assert blocked.action == "blocked"


def test_estimate_override_drives_block(simple_schedule):
    outcome = guard_run(
        ["x"],
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        history=HistoryStore(":memory:"),
        tz=simple_schedule.tz,
        safety_factor=1.0,
        estimate_override=100_000,  # ~27h, can't fit anywhere soon
        now_fn=lambda: dt(2026, 6, 16, 12),
    )
    assert outcome.action == "blocked"
    assert outcome.estimate_source == "override"


# --- guard_run: real execution path (fake runner) ---------------------------
def test_runs_and_records_history(simple_schedule):
    history = HistoryStore(":memory:")
    outcome = guard_run(
        ["echo", "hi"],
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        history=history,
        tz=simple_schedule.tz,
        safety_factor=1.0,
        estimate_override=60,
        now_fn=lambda: dt(2026, 6, 16, 12),
        runner=lambda argv: 0,
    )
    assert outcome.action == "ran"
    assert outcome.exit_code == 0
    assert outcome.command_exit_code == 0
    assert history.count() == 1
    assert history.durations_for("echo") != []  # recorded as ok


def test_failing_command_propagates_code_and_marks_fail(simple_schedule):
    history = HistoryStore(":memory:")
    outcome = guard_run(
        ["false"],
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        history=history,
        tz=simple_schedule.tz,
        safety_factor=1.0,
        estimate_override=60,
        now_fn=lambda: dt(2026, 6, 16, 12),
        runner=lambda argv: 3,
    )
    assert outcome.exit_code == 3
    assert history.durations_for("false") == []  # failures excluded


# --- guard_run: wait mode ---------------------------------------------------
def test_wait_mode_sleeps_then_runs(simple_schedule):
    sleeps: list[float] = []
    ran: list[list[str]] = []
    clock = FakeClock(
        dt(2026, 6, 16, 15),  # initial: power out
        dt(2026, 6, 16, 15),  # loop check: still before safe_start -> sleep
        dt(2026, 6, 16, 16),  # loop check: reached safe window -> go
        dt(2026, 6, 16, 16),  # started_at inside _go
    )
    outcome = guard_run(
        ["docker", "build", "."],
        oracle=_oracle(simple_schedule),
        duration_oracle=_duration(),
        history=HistoryStore(":memory:"),
        tz=simple_schedule.tz,
        safety_factor=1.0,
        estimate_override=1800,  # 30min, fits the 6h post-16:00 window
        wait=True,
        now_fn=clock,
        sleep_fn=lambda s: sleeps.append(s),
        runner=lambda argv: ran.append(argv) or 0,
    )
    assert outcome.action == "ran"
    assert ran == [["docker", "build", "."]]
    assert len(sleeps) >= 1
