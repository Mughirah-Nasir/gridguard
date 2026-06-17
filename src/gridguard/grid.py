"""The grid oracle: time-aware queries over a :class:`Schedule`.

Given a schedule and a reference moment ``now``, the oracle answers:

* :meth:`is_off`           -- is power out right now?
* :meth:`current_window`   -- which cut are we inside (if any)?
* :meth:`next_window_after`-- the next future cut.
* :meth:`runway`           -- how long until power goes off.
* :meth:`next_safe_start`  -- the earliest future moment with enough runway
                              to fit a command of a given length.

All calculations work over a finite *horizon* (default 14 days) so we never
expand an infinite recurring schedule. If no cut exists within the horizon,
runway is reported as ``None`` meaning "effectively unlimited".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .schedule import OutageWindow, Schedule


class GridOracle:
    def __init__(self, schedule: Schedule, horizon_days: int = 14) -> None:
        if horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")
        self.schedule = schedule
        self.horizon_days = horizon_days

    # ------------------------------------------------------------------ #
    def _windows(self, now: datetime) -> list[OutageWindow]:
        start: date = now.date()
        end: date = (now + timedelta(days=self.horizon_days)).date()
        return self.schedule.merged(start, end)

    # ------------------------------------------------------------------ #
    def is_off(self, now: datetime) -> bool:
        """True if ``now`` falls inside any (merged) outage window."""
        return any(w.contains(now) for w in self._windows(now))

    def is_on(self, now: datetime) -> bool:
        return not self.is_off(now)

    def current_window(self, now: datetime) -> OutageWindow | None:
        for w in self._windows(now):
            if w.contains(now):
                return w
        return None

    def next_window_after(self, now: datetime) -> OutageWindow | None:
        """The first outage window that starts strictly after ``now``."""
        for w in self._windows(now):
            if w.start > now:
                return w
        return None

    # ------------------------------------------------------------------ #
    def runway(self, now: datetime) -> timedelta | None:
        """Time until power goes off.

        * If power is currently off  -> ``timedelta(0)``.
        * If a future cut exists      -> time until that cut starts.
        * If no cut within horizon    -> ``None`` (treat as unlimited).
        """
        if self.is_off(now):
            return timedelta(0)
        nxt = self.next_window_after(now)
        if nxt is None:
            return None
        return nxt.start - now

    # ------------------------------------------------------------------ #
    def next_safe_start(self, now: datetime, needed: timedelta) -> datetime | None:
        """Earliest moment >= ``now`` where a command of length ``needed`` fits.

        Runway is a saw-tooth: it jumps up the instant a cut ends and decays
        linearly until the next cut begins. The only moments worth testing are
        therefore ``now`` itself and the end of each outage window. We return
        the first candidate at which power is on *and* runway is large enough.
        """
        windows = self._windows(now)

        candidates: list[datetime] = [now]
        for w in windows:
            if w.end > now:
                candidates.append(w.end)
        candidates = sorted(set(candidates))

        for moment in candidates:
            if self.is_off(moment):
                continue
            r = self.runway(moment)
            if r is None or r >= needed:
                return moment
        return None

    # ------------------------------------------------------------------ #
    def longest_uptime_gap(self, now: datetime) -> timedelta | None:
        """The largest stretch of continuous power within the horizon.

        Used to produce a helpful message when a command simply cannot fit any
        window (e.g. it needs 5h but cuts never leave more than 4h of uptime).
        Returns ``None`` when there is an unbounded tail (no further cuts).
        """
        windows = self._windows(now)
        if not windows:
            return None

        future = [w for w in windows if w.end > now]
        if not future:
            return None

        biggest = timedelta(0)
        # Gap before the first future cut (only if power is currently on).
        if not self.is_off(now) and future[0].start > now:
            biggest = max(biggest, future[0].start - now)

        for i in range(len(future) - 1):
            gap = future[i + 1].start - future[i].end
            if gap > biggest:
                biggest = gap
        # There is always an unbounded tail after the last horizon cut.
        return None if biggest == timedelta(0) else biggest
