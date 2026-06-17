"""Tests for the FastAPI dashboard (skipped if extras aren't installed)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from gridguard.config import Config  # noqa: E402
from gridguard.dashboard.app import create_app  # noqa: E402

_SCHEDULE = """{
  "version": 1, "timezone": "Asia/Karachi", "zone": "DASH-TEST",
  "description": "test feeder",
  "recurring": [{"days": "daily", "start": "14:00", "end": "16:00"}]
}"""


@pytest.fixture()
def client(tmp_path):
    sched = tmp_path / "sched.json"
    sched.write_text(_SCHEDULE, encoding="utf-8")
    config = Config(
        zone="DASH-TEST",
        schedule_path=sched,
        database_path=tmp_path / "history.db",
    )
    return TestClient(create_app(config))


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "GRID" in r.text and "GUARD" in r.text


def test_status_endpoint(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["zone"] == "DASH-TEST"
    assert isinstance(data["power_on"], bool)
    assert "runway_seconds" in data


def test_schedule_endpoint(client):
    r = client.get("/api/schedule?hours=24")
    assert r.status_code == 200
    data = r.json()
    assert data["zone"] == "DASH-TEST"
    assert isinstance(data["windows"], list)
    # a daily 14-16 cut must appear at least once within 24h
    assert len(data["windows"]) >= 1


def test_history_endpoint_empty(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == {"runs": []}


def test_schedule_hours_out_of_range_rejected(client):
    assert client.get("/api/schedule?hours=0").status_code == 422
    assert client.get("/api/schedule?hours=9999").status_code == 422


def test_schedule_hours_upper_bound_accepted(client):
    assert client.get("/api/schedule?hours=168").status_code == 200


def test_history_limit_out_of_range_rejected(client):
    assert client.get("/api/history?limit=0").status_code == 422
    assert client.get("/api/history?limit=9999").status_code == 422


def test_history_limit_in_range_accepted(client):
    assert client.get("/api/history?limit=500").status_code == 200
