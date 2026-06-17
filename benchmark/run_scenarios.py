"""Scenario benchmark for GridGuard's decision core.

Run from the repository root::

    python -m benchmark.run_scenarios

Times three hot paths on synthetic but realistic data and prints the
throughput measured *on this machine*. Numbers vary with hardware and
Python version; nothing here is a documented performance claim.
"""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gridguard.grid import GridOracle
from gridguard.runner import plan_guard
from gridguard.schedule import Schedule

_TZ = ZoneInfo("Asia/Karachi")

_SCHEDULE = Schedule.from_dict(
    {
        "version": 1,
        "zone": "BENCH-Z1",
        "timezone": "Asia/Karachi",
        "recurring": [
            {"days": "daily", "start": "02:00", "end": "04:00", "reason": "night"},
            {"days": "daily", "start": "14:00", "end": "16:00", "reason": "afternoon"},
            {"days": "mon|wed|fri", "start": "20:00", "end": "22:00", "reason": "peak"},
            {"days": "sat|sun", "start": "23:00", "end": "01:00", "reason": "weekend"},
        ],
        "one_off": [
            {
                "date": "2026-06-20",
                "start": "09:00",
                "end": "13:00",
                "reason": "maintenance",
            }
        ],
    }
)


def _timeit(label: str, fn, n: int, repeats: int = 3) -> None:
    """Run ``fn`` ``n`` times, ``repeats`` rounds; report the best round."""
    rates = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        elapsed = time.perf_counter() - t0
        rates.append(n / elapsed)
    best = max(rates)
    spread = statistics.pstdev(rates) / statistics.mean(rates) * 100
    print(
        f"{label:<38} {best:>12,.0f} ops/s   (±{spread:.0f}% across {repeats} rounds)"
    )


def main() -> None:
    oracle = GridOracle(_SCHEDULE)
    now = datetime(2026, 6, 16, 12, 30, tzinfo=_TZ)
    needed = timedelta(minutes=25)

    print("GridGuard decision-core benchmark (synthetic schedule, this machine only)\n")

    _timeit(
        "plan_guard() go/blocked decision",
        lambda: plan_guard(now, oracle, needed),
        20_000,
    )
    _timeit(
        "Schedule.expand() over a 14-day range",
        lambda: _SCHEDULE.expand(now.date(), (now + timedelta(days=14)).date()),
        2_000,
    )
    _timeit(
        "GridOracle.next_safe_start()",
        lambda: oracle.next_safe_start(now, needed),
        5_000,
    )

    print(
        "\nNumbers depend on hardware, load and Python version -- treat them as\n"
        "relative indicators, not guarantees."
    )


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:  # output piped to e.g. `head` -- not an error
        import os

        os._exit(0)
