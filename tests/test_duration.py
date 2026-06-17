"""Tests for the duration oracle and percentile helper."""

from __future__ import annotations

import pytest

from gridguard.duration import DurationOracle, normalize_signature, percentile
from gridguard.history import HistoryStore
from tests.conftest import dt


# --- signature normalisation ------------------------------------------------
@pytest.mark.parametrize(
    "argv,expected",
    [
        (["docker", "build", "-t", "app", "."], "docker build"),
        (["git", "push", "origin", "main"], "git push"),
        (["npm", "run", "build"], "npm run"),
        (["pytest"], "pytest"),
        (["/usr/bin/docker", "build", "."], "docker build"),
        (["docker.exe", "compose", "up"], "docker compose"),
        (["git", "-C", "/repo", "status"], "git status"),  # skips the -C flag
        (["python", "-m", "pytest"], "python pytest"),
        ([], ""),
    ],
)
def test_normalize_signature(argv, expected):
    assert normalize_signature(argv) == expected


# --- percentile -------------------------------------------------------------
def test_percentile_single_value():
    assert percentile([42.0], 90) == 42.0


def test_percentile_interpolation():
    # numpy linear method: p90 of [10,20,30,40] -> rank 2.7 -> 37.0
    assert percentile([10, 20, 30, 40], 90) == pytest.approx(37.0)


def test_percentile_median():
    assert percentile([10, 20, 30], 50) == pytest.approx(20.0)


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 90)


def test_percentile_out_of_range():
    with pytest.raises(ValueError):
        percentile([1, 2], 150)


# --- estimate source selection ---------------------------------------------
def _record(history, sig_argv, durations):
    for d in durations:
        history.record(
            signature=normalize_signature(sig_argv),
            raw_command=" ".join(sig_argv),
            started_at=dt(2026, 6, 16, 12),
            duration_s=d,
            exit_code=0,
            outcome="ok",
        )


def test_estimate_uses_history_when_enough_samples():
    h = HistoryStore(":memory:")
    _record(h, ["docker", "build", "."], [100, 110, 120, 130])
    oracle = DurationOracle(h, min_samples=3, percentile_value=90)
    est = oracle.estimate(["docker", "build", "."])
    assert est.source == "history"
    assert est.samples == 4
    assert est.seconds == pytest.approx(127.0)  # p90 of the four samples


def test_estimate_falls_back_to_config_below_min_samples():
    h = HistoryStore(":memory:")
    _record(h, ["docker", "build", "."], [100, 110])  # only 2 samples
    oracle = DurationOracle(h, min_samples=3, defaults={"docker build": 600.0})
    est = oracle.estimate(["docker", "build", "."])
    assert est.source == "config"
    assert est.seconds == 600.0


def test_estimate_global_fallback():
    h = HistoryStore(":memory:")
    oracle = DurationOracle(h, fallback_seconds=42.0)
    est = oracle.estimate(["mystery-tool"])
    assert est.source == "fallback"
    assert est.seconds == 42.0


def test_failed_runs_excluded_from_history():
    h = HistoryStore(":memory:")
    # 4 fast failures should NOT make the estimate think the build is fast.
    for _ in range(4):
        h.record(
            signature="docker build",
            raw_command="docker build .",
            started_at=dt(2026, 6, 16, 12),
            duration_s=2.0,
            exit_code=1,
            outcome="fail",
        )
    oracle = DurationOracle(h, min_samples=3, fallback_seconds=300.0)
    est = oracle.estimate(["docker", "build", "."])
    assert est.source == "fallback"  # no successful samples -> fallback
