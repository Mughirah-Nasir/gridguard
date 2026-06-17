"""The guard itself: decide whether to run a command, then run it.

The logic is split in two so the *decision* can be unit-tested without ever
launching a subprocess:

* :func:`plan_guard` is a **pure function**: given ``now``, an oracle, and how
  much runway a command needs, it returns a :class:`GuardPlan` describing what
  to do. No side effects, no clock reads, fully deterministic.
* :func:`guard_run` wraps that: it asks the duration oracle for an estimate,
  builds the plan, and then either runs the command (timing it and recording
  the result) or refuses with exit code 87 -- optionally *waiting* until a safe
  window in ``--wait`` mode.

Clock and sleep are injected (``now_fn`` / ``sleep_fn``) so tests can simulate
hours passing in microseconds.
"""

from __future__ import annotations

import subprocess
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from .duration import DurationOracle, normalize_signature
from .exit_codes import ExitCode
from .grid import GridOracle
from .history import HistoryStore
from .schedule import OutageWindow

# Type aliases for the injectable clock/sleep/runner.
NowFn = Callable[[], datetime]
SleepFn = Callable[[float], None]
RunnerFn = Callable[[list[str]], int]


def _default_runner(argv: list[str]) -> int:
    """Run a command, inheriting this process's stdio, and return its code."""
    return subprocess.run(argv).returncode


@dataclass(frozen=True, slots=True)
class GuardPlan:
    action: str  # "go" | "blocked-runway" | "blocked-power-off"
    needed: timedelta
    runway: timedelta | None
    now: datetime
    current_outage: OutageWindow | None
    next_outage: OutageWindow | None
    safe_start: datetime | None

    @property
    def blocked(self) -> bool:
        return self.action != "go"


def plan_guard(now: datetime, oracle: GridOracle, needed: timedelta) -> GuardPlan:
    """Decide what to do with a command needing ``needed`` of runway. Pure."""
    if oracle.is_off(now):
        return GuardPlan(
            action="blocked-power-off",
            needed=needed,
            runway=timedelta(0),
            now=now,
            current_outage=oracle.current_window(now),
            next_outage=oracle.next_window_after(now),
            safe_start=oracle.next_safe_start(now, needed),
        )

    runway = oracle.runway(now)
    if runway is None or runway >= needed:
        return GuardPlan(
            action="go",
            needed=needed,
            runway=runway,
            now=now,
            current_outage=None,
            next_outage=oracle.next_window_after(now),
            safe_start=now,
        )

    return GuardPlan(
        action="blocked-runway",
        needed=needed,
        runway=runway,
        now=now,
        current_outage=None,
        next_outage=oracle.next_window_after(now),
        safe_start=oracle.next_safe_start(now, needed),
    )


@dataclass(slots=True)
class RunOutcome:
    action: str  # "ran" | "would-run" | "blocked"
    exit_code: int
    message: str
    estimate_seconds: float
    estimate_source: str
    plan: GuardPlan
    command_exit_code: int | None = None


def _fmt_delta(delta: timedelta | None) -> str:
    if delta is None:
        return "unlimited"
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{sign}{h}h{m:02d}m"
    if m:
        return f"{sign}{m}m{s:02d}s"
    return f"{sign}{s}s"


def _fmt_time(moment: datetime | None) -> str:
    return moment.strftime("%a %H:%M") if moment else "n/a"


def guard_run(
    argv: list[str],
    *,
    oracle: GridOracle,
    duration_oracle: DurationOracle,
    history: HistoryStore,
    tz: ZoneInfo,
    safety_factor: float,
    estimate_override: float | None = None,
    dry_run: bool = False,
    wait: bool = False,
    now_fn: NowFn | None = None,
    sleep_fn: SleepFn = _time.sleep,
    runner: RunnerFn = _default_runner,
    wait_poll_seconds: float = 30.0,
) -> RunOutcome:
    """Guard and (optionally) run ``argv``. Returns a :class:`RunOutcome`."""
    if not argv:
        raise ValueError("no command supplied to guard_run")

    now_fn = now_fn or (lambda: datetime.now(tz))

    if estimate_override is not None:
        est_seconds, est_source = float(estimate_override), "override"
    else:
        est = duration_oracle.estimate(argv)
        est_seconds, est_source = est.seconds, est.source

    needed = timedelta(seconds=est_seconds * safety_factor)
    now = now_fn()
    plan = plan_guard(now, oracle, needed)

    if plan.action == "go":
        return _go(
            argv,
            plan,
            history,
            duration_oracle,
            runner,
            now_fn,
            est_seconds,
            est_source,
            dry_run,
        )

    # --- blocked ----------------------------------------------------------
    if not wait:
        return RunOutcome(
            action="blocked",
            exit_code=int(ExitCode.BLOCKED),
            message=_blocked_message(plan, est_seconds),
            estimate_seconds=est_seconds,
            estimate_source=est_source,
            plan=plan,
        )

    # --- wait mode: sleep until a safe window, re-checking as we go -------
    target = plan.safe_start
    if target is None:
        return RunOutcome(
            action="blocked",
            exit_code=int(ExitCode.BLOCKED),
            message=(
                f"no safe window within {oracle.horizon_days} days: command "
                f"needs ~{_fmt_delta(needed)} of uptime but none is long enough."
            ),
            estimate_seconds=est_seconds,
            estimate_source=est_source,
            plan=plan,
        )

    while True:
        now = now_fn()
        if now >= target:
            plan = plan_guard(now, oracle, needed)
            if plan.action == "go":
                return _go(
                    argv,
                    plan,
                    history,
                    duration_oracle,
                    runner,
                    now_fn,
                    est_seconds,
                    est_source,
                    dry_run,
                )
            target = plan.safe_start
            if target is None:
                return RunOutcome(
                    action="blocked",
                    exit_code=int(ExitCode.BLOCKED),
                    message="no safe window found after waiting.",
                    estimate_seconds=est_seconds,
                    estimate_source=est_source,
                    plan=plan,
                )
            continue
        remaining = (target - now).total_seconds()
        sleep_fn(min(remaining, wait_poll_seconds))


def _go(
    argv,
    plan,
    history,
    duration_oracle,
    runner,
    now_fn,
    est_seconds,
    est_source,
    dry_run,
) -> RunOutcome:
    runway_txt = _fmt_delta(plan.runway)
    if dry_run:
        return RunOutcome(
            action="would-run",
            exit_code=int(ExitCode.OK),
            message=(
                f"OK to run: ~{_fmt_delta(plan.needed)} needed, "
                f"{runway_txt} runway before next cut "
                f"({_fmt_time(plan.next_outage.start) if plan.next_outage else 'none'})."
            ),
            estimate_seconds=est_seconds,
            estimate_source=est_source,
            plan=plan,
        )

    started_at = now_fn()
    t0 = _time.monotonic()
    code = runner(argv)
    duration = _time.monotonic() - t0

    history.record(
        signature=normalize_signature(argv),
        raw_command=" ".join(argv),
        started_at=started_at,
        duration_s=duration,
        exit_code=code,
        outcome="ok" if code == 0 else "fail",
    )

    return RunOutcome(
        action="ran",
        exit_code=code,
        message=(
            f"command finished in {_fmt_delta(timedelta(seconds=duration))} "
            f"with exit code {code}."
        ),
        estimate_seconds=est_seconds,
        estimate_source=est_source,
        plan=plan,
        command_exit_code=code,
    )


def _blocked_message(plan: GuardPlan, est_seconds: float) -> str:
    needed = _fmt_delta(plan.needed)
    if plan.safe_start is None:
        hint = (
            f"no uptime window within the horizon is long enough for ~{needed}; "
            f"check the schedule or lower the estimate."
        )
    else:
        hint = (
            f"Next safe start: {_fmt_time(plan.safe_start)}. "
            f"Re-run with --wait to start automatically."
        )
    if plan.action == "blocked-power-off":
        until = _fmt_time(plan.current_outage.end) if plan.current_outage else "?"
        return (
            f"power is OUT right now (cut until {until}). "
            f"Command needs ~{needed}. {hint}"
        )
    # blocked-runway
    runway = _fmt_delta(plan.runway)
    nxt = _fmt_time(plan.next_outage.start) if plan.next_outage else "?"
    return (
        f"only {runway} of runway before the next cut at {nxt}, but the "
        f"command needs ~{needed}. {hint}"
    )
