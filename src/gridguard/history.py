"""Persistent history of guarded command runs (SQLite).

Every time GridGuard actually executes a command it records how long it took.
That history is what makes the :mod:`gridguard.duration` oracle smart: instead
of guessing how long ``docker build`` takes, it learns from your machine.

The store is intentionally tiny -- one table, plain ``sqlite3`` from the
standard library, no ORM. SQLite is a single file, needs no server, and is
already perfect for a local developer tool.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signature   TEXT    NOT NULL,
    raw_command TEXT    NOT NULL,
    started_at  TEXT    NOT NULL,
    duration_s  REAL    NOT NULL,
    exit_code   INTEGER NOT NULL,
    outcome     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_signature ON runs(signature);
"""


class HistoryStore:
    """A small SQLite store of past runs.

    Pass ``":memory:"`` for an ephemeral in-process database (used in tests).
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the FastAPI dashboard can read it too.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ #
    def record(
        self,
        *,
        signature: str,
        raw_command: str,
        started_at: datetime,
        duration_s: float,
        exit_code: int,
        outcome: str,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs "
            "(signature, raw_command, started_at, duration_s, exit_code, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                signature,
                raw_command,
                started_at.isoformat(),
                float(duration_s),
                int(exit_code),
                outcome,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ------------------------------------------------------------------ #
    def durations_for(self, signature: str, limit: int | None = None) -> list[float]:
        """Return successful-run durations for a signature, most recent first.

        Only ``outcome == 'ok'`` rows count towards the duration estimate -- a
        build that crashed after 3 seconds should not make GridGuard think the
        build is fast.
        """
        sql = (
            "SELECT duration_s FROM runs "
            "WHERE signature = ? AND outcome = 'ok' "
            "ORDER BY id DESC"
        )
        params: tuple = (signature,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (signature, int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [float(r["duration_s"]) for r in rows]

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "HistoryStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
