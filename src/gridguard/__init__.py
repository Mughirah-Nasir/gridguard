"""GridGuard -- a grid-aware command guard for load-shedding environments.

GridGuard wraps long-running commands (Docker builds, database migrations,
large Git operations) and refuses to start them when a power cut would land
mid-run, exiting with the reserved code 87 instead. It learns how long your
commands take and consults a load-shedding schedule to decide whether each
command can finish before the next cut.
"""

from __future__ import annotations

from .config import Config
from .duration import DurationOracle, Estimate, normalize_signature, percentile
from .exit_codes import GRID_BLOCKED, ExitCode
from .grid import GridOracle
from .history import HistoryStore
from .runner import GuardPlan, RunOutcome, guard_run, plan_guard
from .schedule import OutageWindow, Schedule, ScheduleError

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "Config",
    "DurationOracle",
    "Estimate",
    "ExitCode",
    "GRID_BLOCKED",
    "GridOracle",
    "GuardPlan",
    "HistoryStore",
    "OutageWindow",
    "RunOutcome",
    "Schedule",
    "ScheduleError",
    "guard_run",
    "normalize_signature",
    "percentile",
    "plan_guard",
]
