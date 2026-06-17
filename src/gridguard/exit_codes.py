"""Exit codes used across the GridGuard CLI.

The single most important value here is ``BLOCKED = 87``.

When GridGuard refuses to start a command because there is not enough
"runway" (mains uptime) before the next load-shedding window, it exits with
code ``87`` *instead of* running your command. That lets a calling script,
Makefile, or CI step distinguish "GridGuard stopped this on purpose" from
"the command itself failed". 87 is deliberately outside the range that
common tools use (git/docker/npm tend to use 1, 2, 125, 128+), so collisions
are very unlikely. 87 is reserved: if a guarded command happens to exit 87
itself, GridGuard still reports that as the command's own result and notes
the ambiguity in the run record.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes returned by ``gridguard``."""

    OK = 0
    #: A usage / argument error (bad flags, missing command, bad schedule).
    USAGE = 2
    #: GridGuard intentionally blocked the command. The wrapped command did
    #: NOT run. This is the load-shedding sentinel.
    BLOCKED = 87


#: Public alias so callers can ``from gridguard import GRID_BLOCKED``.
GRID_BLOCKED: int = int(ExitCode.BLOCKED)
