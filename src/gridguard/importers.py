"""Import load-shedding schedules from CSV (and validate native JSON).

Distribution companies and WhatsApp groups publish load-shedding rotas as
plain tables far more often than as JSON. The CSV importer lets you paste such
a table into a spreadsheet, export it, and convert it into GridGuard's native
schedule format.

CSV format (header row required)::

    type,days,date,start,end,reason
    recurring,daily,,02:00,04:00,scheduled load-shedding
    recurring,mon|wed|fri,,20:00,22:00,peak-hour shedding
    oneoff,,2026-06-15,09:00,13:00,grid maintenance

Rules:

* ``type`` is ``recurring`` or ``oneoff``.
* recurring rows use ``days`` (``daily`` or pipe-separated mon..sun); ``date``
  is blank.
* oneoff rows use ``date`` (YYYY-MM-DD); ``days`` is blank.
* ``reason`` is optional.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .schedule import Schedule, ScheduleError

_REQUIRED_COLUMNS = {"type", "start", "end"}


def schedule_from_csv(
    text: str,
    *,
    zone: str,
    timezone: str = "Asia/Karachi",
    description: str = "",
) -> Schedule:
    """Parse the GridGuard CSV format into a :class:`Schedule`."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ScheduleError("empty CSV: a header row is required")
    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = _REQUIRED_COLUMNS - headers
    if missing:
        raise ScheduleError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}"
        )

    recurring: list[dict] = []
    one_off: list[dict] = []

    for lineno, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not any(row.values()):
            continue  # skip blank lines
        rtype = row.get("type", "").lower()
        start = row.get("start", "")
        end = row.get("end", "")
        reason = row.get("reason") or "load-shedding"

        if not start or not end:
            raise ScheduleError(f"row {lineno}: start and end are required")

        if rtype == "recurring":
            days = row.get("days", "")
            if not days:
                raise ScheduleError(f"row {lineno}: recurring rows need a 'days' value")
            recurring.append(
                {"days": days, "start": start, "end": end, "reason": reason}
            )
        elif rtype == "oneoff":
            day = row.get("date", "")
            if not day:
                raise ScheduleError(
                    f"row {lineno}: oneoff rows need a 'date' (YYYY-MM-DD)"
                )
            one_off.append({"date": day, "start": start, "end": end, "reason": reason})
        else:
            raise ScheduleError(
                f"row {lineno}: unknown type {rtype!r} "
                f"(expected 'recurring' or 'oneoff')"
            )

    return Schedule.from_dict(
        {
            "version": 1,
            "timezone": timezone,
            "zone": zone,
            "description": description,
            "recurring": recurring,
            "one_off": one_off,
        }
    )


def load_any(
    path: str | Path,
    *,
    fmt: str | None = None,
    zone: str | None = None,
    timezone: str = "Asia/Karachi",
) -> Schedule:
    """Load a schedule from a file, auto-detecting CSV vs JSON by extension."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    chosen = (fmt or p.suffix.lstrip(".")).lower()
    if chosen == "csv":
        if not zone:
            raise ScheduleError("CSV import requires --zone")
        return schedule_from_csv(text, zone=zone, timezone=timezone)
    return Schedule.from_json(text)
