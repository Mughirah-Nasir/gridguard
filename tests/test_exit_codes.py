"""Tests for the exit-code enum."""

from __future__ import annotations

from gridguard.exit_codes import GRID_BLOCKED, ExitCode


def test_blocked_is_87():
    assert ExitCode.BLOCKED == 87
    assert GRID_BLOCKED == 87


def test_ok_and_usage_values():
    assert ExitCode.OK == 0
    assert ExitCode.USAGE == 2


def test_exit_codes_are_ints():
    # IntEnum members must be usable directly as process return codes.
    assert int(ExitCode.BLOCKED) == 87
    assert isinstance(ExitCode.BLOCKED.value, int)
