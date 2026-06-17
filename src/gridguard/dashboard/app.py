"""FastAPI dashboard for GridGuard (optional extra).

Serves a single dark "control-room" page plus three JSON endpoints the page
polls:

* ``GET /api/status``   -- current power state, runway, current/next cut.
* ``GET /api/schedule`` -- upcoming cuts for the next 48 hours.
* ``GET /api/history``  -- recent guarded runs.

Kept dependency-light: the page is a static HTML file read from disk and
returned as-is, so no template engine is required.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import Config
from ..grid import GridOracle
from ..history import HistoryStore
from ..schedule import Schedule

_TEMPLATE = Path(__file__).parent / "templates" / "index.html"


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="GridGuard", version="1.0.0")

    def schedule() -> Schedule:
        return Schedule.load(config.schedule_path)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _TEMPLATE.read_text(encoding="utf-8")

    @app.get("/api/status")
    def status() -> JSONResponse:
        sched = schedule()
        oracle = GridOracle(sched, horizon_days=config.horizon_days)
        now = datetime.now(sched.tz)
        runway = oracle.runway(now)
        current = oracle.current_window(now)
        nxt = oracle.next_window_after(now)
        return JSONResponse(
            {
                "zone": sched.zone,
                "description": sched.description,
                "now": now.isoformat(),
                "power_on": oracle.is_on(now),
                "runway_seconds": None if runway is None else runway.total_seconds(),
                "current_outage": current.to_dict() if current else None,
                "next_outage": nxt.to_dict() if nxt else None,
            }
        )

    @app.get("/api/schedule")
    def upcoming(hours: int = Query(48, ge=1, le=168)) -> JSONResponse:
        sched = schedule()
        now = datetime.now(sched.tz)
        window_end = now + timedelta(hours=hours)
        windows = [
            w
            for w in sched.merged(now.date(), window_end.date())
            if w.end > now and w.start < window_end
        ]
        return JSONResponse(
            {
                "zone": sched.zone,
                "hours": hours,
                "now": now.isoformat(),
                "windows": [w.to_dict() for w in windows],
            }
        )

    @app.get("/api/history")
    def history(limit: int = Query(20, ge=1, le=500)) -> JSONResponse:
        store = HistoryStore(config.database_path)
        rows = store.recent(limit)
        store.close()
        return JSONResponse({"runs": rows})

    return app
