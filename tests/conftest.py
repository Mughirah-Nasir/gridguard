"""Shared fixtures and helpers for the GridGuard test-suite."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gridguard.schedule import Schedule

KHI = ZoneInfo("Asia/Karachi")


def dt(y, mo, d, h, mi=0, s=0):
    """Build a Karachi-timezone datetime."""
    return datetime(y, mo, d, h, mi, s, tzinfo=KHI)


@pytest.fixture()
def simple_schedule() -> Schedule:
    """Daily cuts 14:00-16:00 and 22:00-00:00 (crosses midnight)."""
    return Schedule.from_dict(
        {
            "version": 1,
            "timezone": "Asia/Karachi",
            "zone": "TEST-Z1",
            "recurring": [
                {
                    "days": "daily",
                    "start": "14:00",
                    "end": "16:00",
                    "reason": "afternoon",
                },
                {"days": "daily", "start": "22:00", "end": "00:00", "reason": "night"},
            ],
            "one_off": [
                {
                    "date": "2026-06-20",
                    "start": "09:00",
                    "end": "11:00",
                    "reason": "maintenance",
                },
            ],
        }
    )
