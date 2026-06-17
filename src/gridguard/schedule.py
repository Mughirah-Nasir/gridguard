"""Load-shedding schedule model.

A :class:`Schedule` describes when mains power is *off* for one feeder/zone.
Two kinds of rules are supported:

* **recurring** rules repeat on given weekdays (e.g. every day 14:00-16:00).
* **one_off** rules apply to a single calendar date (e.g. announced grid
  maintenance on 2026-06-15 09:00-13:00).

The schedule stores *outages* (power-off windows). Everything not covered by
an outage window is assumed to be powered. Windows may cross midnight
(start 22:00, end 02:00) -- this is handled when rules are expanded into
concrete :class:`OutageWindow` objects for a date range.

Design note
-----------
We model outages rather than "uptime" because that is how every Pakistani
distribution company (IESCO/LESCO/K-Electric) actually publishes load-shedding:
as a small set of cut windows per feeder. Storing the complement (uptime)
would be larger and harder to author by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1

_WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
_DAILY = "daily"


class ScheduleError(ValueError):
    """Raised when a schedule definition is malformed."""


def _parse_time(value: str) -> time:
    """Parse ``HH:MM`` (24-hour) into a :class:`datetime.time`."""
    try:
        hh, mm = value.strip().split(":")
        return time(hour=int(hh), minute=int(mm))
    except Exception as exc:  # noqa: BLE001 - re-raise as schedule error
        raise ScheduleError(f"invalid time {value!r}, expected HH:MM") from exc


def _parse_days(days: Iterable[str] | str) -> list[int]:
    """Normalise a day specification into a sorted list of weekday indices.

    Accepts the literal ``"daily"`` or any iterable / pipe-joined string of
    short day names (``mon|wed|fri`` or ``["mon", "wed"]``).
    """
    if isinstance(days, str):
        token = days.strip().lower()
        if token == _DAILY or token == "*" or token == "all":
            return list(range(7))
        parts = [p for p in token.replace(",", "|").split("|") if p]
    else:
        parts = [str(d).strip().lower() for d in days]

    if not parts:
        raise ScheduleError("no days specified for recurring rule")

    out: set[int] = set()
    for part in parts:
        if part == _DAILY:
            out.update(range(7))
            continue
        if part not in _WEEKDAYS:
            raise ScheduleError(f"unknown day {part!r}; use mon..sun or 'daily'")
        out.add(_WEEKDAYS[part])
    return sorted(out)


@dataclass(frozen=True, slots=True)
class OutageWindow:
    """A concrete power-off window with timezone-aware endpoints.

    Invariant: ``start < end``. The window is half-open ``[start, end)`` so a
    cut ending at 16:00 means power is back exactly at 16:00:00.
    """

    start: datetime
    end: datetime
    reason: str = "load-shedding"
    source: str = "recurring"  # "recurring" | "one_off"

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ScheduleError(
                f"outage window start {self.start} must be before end {self.end}"
            )

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class RecurringRule:
    days: tuple[int, ...]
    start: time
    end: time
    reason: str = "load-shedding"

    def crosses_midnight(self) -> bool:
        return self.end <= self.start


@dataclass(frozen=True, slots=True)
class OneOffRule:
    day: date
    start: time
    end: time
    reason: str = "load-shedding"

    def crosses_midnight(self) -> bool:
        return self.end <= self.start


@dataclass(slots=True)
class Schedule:
    """A full load-shedding schedule for a single zone/feeder."""

    zone: str
    tz: ZoneInfo
    recurring: list[RecurringRule] = field(default_factory=list)
    one_off: list[OneOffRule] = field(default_factory=list)
    description: str = ""

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: dict) -> "Schedule":
        version = data.get("version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ScheduleError(
                f"unsupported schedule version {version!r}; expected {SCHEMA_VERSION}"
            )

        tz_name = data.get("timezone", "Asia/Karachi")
        try:
            tz = ZoneInfo(tz_name)
        except Exception as exc:  # noqa: BLE001
            raise ScheduleError(f"unknown timezone {tz_name!r}") from exc

        zone = data.get("zone")
        if not zone:
            raise ScheduleError("schedule must declare a 'zone'")

        recurring: list[RecurringRule] = []
        for raw in data.get("recurring", []):
            recurring.append(
                RecurringRule(
                    days=tuple(_parse_days(raw["days"])),
                    start=_parse_time(raw["start"]),
                    end=_parse_time(raw["end"]),
                    reason=raw.get("reason", "load-shedding"),
                )
            )

        one_off: list[OneOffRule] = []
        for raw in data.get("one_off", []):
            try:
                day = date.fromisoformat(raw["date"])
            except Exception as exc:  # noqa: BLE001
                raise ScheduleError(
                    f"invalid one_off date {raw.get('date')!r}, expected YYYY-MM-DD"
                ) from exc
            one_off.append(
                OneOffRule(
                    day=day,
                    start=_parse_time(raw["start"]),
                    end=_parse_time(raw["end"]),
                    reason=raw.get("reason", "load-shedding"),
                )
            )

        return cls(
            zone=zone,
            tz=tz,
            recurring=recurring,
            one_off=one_off,
            description=data.get("description", ""),
        )

    @classmethod
    def from_json(cls, text: str) -> "Schedule":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ScheduleError(f"invalid JSON schedule: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: str | Path) -> "Schedule":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        inv = {v: k for k, v in _WEEKDAYS.items()}
        return {
            "version": SCHEMA_VERSION,
            "timezone": str(self.tz),
            "zone": self.zone,
            "description": self.description,
            "recurring": [
                {
                    "days": [inv[d] for d in r.days],
                    "start": r.start.strftime("%H:%M"),
                    "end": r.end.strftime("%H:%M"),
                    "reason": r.reason,
                }
                for r in self.recurring
            ],
            "one_off": [
                {
                    "date": o.day.isoformat(),
                    "start": o.start.strftime("%H:%M"),
                    "end": o.end.strftime("%H:%M"),
                    "reason": o.reason,
                }
                for o in self.one_off
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    # ------------------------------------------------------------------ #
    # Expansion
    # ------------------------------------------------------------------ #
    def _combine(self, day: date, start: time, end: time) -> tuple[datetime, datetime]:
        s = datetime.combine(day, start).replace(tzinfo=self.tz)
        e = datetime.combine(day, end).replace(tzinfo=self.tz)
        if end <= start:  # window crosses midnight
            e += timedelta(days=1)
        return s, e

    def expand(self, start: date, end: date) -> list[OutageWindow]:
        """Return concrete outage windows overlapping ``[start 00:00, end+1d 00:00)``.

        We iterate one day **before** ``start`` so a window that began the
        previous evening and crosses midnight into ``start`` is found -- but a
        window from that previous day that *ends before* ``start``'s midnight
        is filtered out, otherwise stale windows from yesterday would leak
        into today's view. Returned windows are sorted by start time but
        **not** merged; use :meth:`merged` for that.
        """
        if end < start:
            raise ScheduleError("expand() end date is before start date")

        range_start = datetime.combine(start, time(0, 0)).replace(tzinfo=self.tz)

        windows: list[OutageWindow] = []

        def _maybe_add(
            day: date, t_start: time, t_end: time, reason: str, source: str
        ) -> None:
            s, e = self._combine(day, t_start, t_end)
            if e > range_start:  # half-open: must actually reach into range
                windows.append(OutageWindow(s, e, reason, source))

        cursor = start - timedelta(days=1)
        while cursor <= end:
            weekday = cursor.weekday()
            for rule in self.recurring:
                if weekday in rule.days:
                    _maybe_add(cursor, rule.start, rule.end, rule.reason, "recurring")
            for rule in self.one_off:
                if rule.day == cursor:
                    _maybe_add(cursor, rule.start, rule.end, rule.reason, "one_off")
            cursor += timedelta(days=1)

        windows.sort(key=lambda w: w.start)
        return windows

    def merged(self, start: date, end: date) -> list[OutageWindow]:
        """Like :meth:`expand` but coalesces overlapping/adjacent windows.

        Adjacent windows (one ends exactly when the next starts) are merged so
        that runway calculations don't see a fake instant of power between
        back-to-back cuts.
        """
        raw = self.expand(start, end)
        if not raw:
            return []
        merged: list[OutageWindow] = [raw[0]]
        for win in raw[1:]:
            last = merged[-1]
            if win.start <= last.end:  # overlapping or adjacent
                if win.end > last.end:
                    reason = (
                        last.reason
                        if last.reason == win.reason
                        else f"{last.reason} + {win.reason}"
                    )
                    merged[-1] = OutageWindow(last.start, win.end, reason, "recurring")
            else:
                merged.append(win)
        return merged
