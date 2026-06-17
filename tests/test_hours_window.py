"""Regression tests for the --hours / ?hours= window filter.

A 1-hour view must not show a cut that starts hours later just because it
falls on the same calendar date; a 24-hour view must show it. The filter is
overlap with [now, now + hours), not date membership.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from gridguard.cli import main

_TZ = ZoneInfo("Asia/Karachi")
_MARKER = "MARKER-CUT-FIVE-HOURS-AWAY"


def _schedule_with_cut_in(hours_from_now: float) -> str:
    """A JSON schedule whose only cut starts ``hours_from_now`` from now."""
    start = datetime.now(_TZ) + timedelta(hours=hours_from_now)
    end = start + timedelta(hours=1)
    return (
        '{"version": 1, "zone": "HOURS-T", "timezone": "Asia/Karachi", '
        '"one_off": [{"date": "%s", "start": "%s", "end": "%s", "reason": "%s"}]}'
        % (
            start.date().isoformat(),
            start.strftime("%H:%M"),
            end.strftime("%H:%M"),
            _MARKER,
        )
    )


def _write_schedule(tmp_path, hours_from_now: float) -> str:
    p = tmp_path / "hours-window.json"
    p.write_text(_schedule_with_cut_in(hours_from_now), encoding="utf-8")
    return str(p)


# --- CLI ---------------------------------------------------------------------
def test_cli_hours_1_hides_cut_five_hours_away(tmp_path, capsys):
    sched = _write_schedule(tmp_path, 5)
    rc = main(["schedule", "show", "--schedule", sched, "--hours", "1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert _MARKER not in out


def test_cli_hours_24_shows_cut_five_hours_away(tmp_path, capsys):
    sched = _write_schedule(tmp_path, 5)
    rc = main(["schedule", "show", "--schedule", sched, "--hours", "24"])
    out = capsys.readouterr().out
    assert rc == 0
    assert _MARKER in out


# --- Dashboard ---------------------------------------------------------------
def _client(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from gridguard.config import Config
    from gridguard.dashboard.app import create_app

    config = Config(
        zone="HOURS-T",
        schedule_path=tmp_path / "hours-window.json",
        database_path=tmp_path / "history.db",
    )
    return TestClient(create_app(config))


def test_dashboard_hours_1_hides_cut_five_hours_away(tmp_path):
    _write_schedule(tmp_path, 5)
    client = _client(tmp_path)
    payload = client.get("/api/schedule?hours=1").json()
    reasons = [w["reason"] for w in payload["windows"]]
    assert _MARKER not in reasons


def test_dashboard_hours_24_shows_cut_five_hours_away(tmp_path):
    _write_schedule(tmp_path, 5)
    client = _client(tmp_path)
    payload = client.get("/api/schedule?hours=24").json()
    reasons = [w["reason"] for w in payload["windows"]]
    assert _MARKER in reasons
