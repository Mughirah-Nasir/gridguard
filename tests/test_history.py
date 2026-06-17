"""Tests for the SQLite history store."""

from __future__ import annotations

from gridguard.history import HistoryStore
from tests.conftest import dt


def test_record_and_count():
    h = HistoryStore(":memory:")
    assert h.count() == 0
    h.record(
        signature="git push",
        raw_command="git push origin main",
        started_at=dt(2026, 6, 16, 12),
        duration_s=30.0,
        exit_code=0,
        outcome="ok",
    )
    assert h.count() == 1


def test_durations_for_only_ok():
    h = HistoryStore(":memory:")
    h.record(
        signature="git push",
        raw_command="git push",
        started_at=dt(2026, 6, 16, 12),
        duration_s=30.0,
        exit_code=0,
        outcome="ok",
    )
    h.record(
        signature="git push",
        raw_command="git push",
        started_at=dt(2026, 6, 16, 13),
        duration_s=5.0,
        exit_code=1,
        outcome="fail",
    )
    assert h.durations_for("git push") == [30.0]


def test_durations_for_most_recent_first():
    h = HistoryStore(":memory:")
    for i, d in enumerate([10.0, 20.0, 30.0]):
        h.record(
            signature="docker build",
            raw_command="docker build .",
            started_at=dt(2026, 6, 16, 12 + i),
            duration_s=d,
            exit_code=0,
            outcome="ok",
        )
    assert h.durations_for("docker build") == [30.0, 20.0, 10.0]


def test_durations_for_respects_limit():
    h = HistoryStore(":memory:")
    for d in [1.0, 2.0, 3.0, 4.0]:
        h.record(
            signature="x",
            raw_command="x",
            started_at=dt(2026, 6, 16, 12),
            duration_s=d,
            exit_code=0,
            outcome="ok",
        )
    assert len(h.durations_for("x", limit=2)) == 2


def test_recent_ordering_and_shape():
    h = HistoryStore(":memory:")
    h.record(
        signature="a",
        raw_command="a one",
        started_at=dt(2026, 6, 16, 12),
        duration_s=1.0,
        exit_code=0,
        outcome="ok",
    )
    h.record(
        signature="b",
        raw_command="b two",
        started_at=dt(2026, 6, 16, 13),
        duration_s=2.0,
        exit_code=0,
        outcome="ok",
    )
    rows = h.recent(10)
    assert rows[0]["raw_command"] == "b two"  # newest first
    assert {
        "signature",
        "raw_command",
        "started_at",
        "duration_s",
        "exit_code",
        "outcome",
    } <= set(rows[0])


def test_persists_to_file(tmp_path):
    db = tmp_path / "nested" / "history.db"
    h = HistoryStore(db)
    h.record(
        signature="a",
        raw_command="a",
        started_at=dt(2026, 6, 16, 12),
        duration_s=1.0,
        exit_code=0,
        outcome="ok",
    )
    h.close()
    assert db.exists()
    h2 = HistoryStore(db)
    assert h2.count() == 1
    h2.close()
