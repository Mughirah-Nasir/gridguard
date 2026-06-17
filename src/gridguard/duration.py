"""The duration oracle: "how long will this command take?"

This is the brain that decides whether a command can finish before the next
power cut. It works in two parts:

1. **Signature normalisation.** ``docker build -t app:latest .`` and
   ``docker build -t app:dev .`` should be treated as the same kind of work.
   We reduce an argv to a stable *signature* like ``"docker build"`` by taking
   the program name plus (for known multi-command tools) its sub-command, and
   dropping all flags and operands.

2. **Estimation.** For a signature we look at past run durations from
   :class:`~gridguard.history.HistoryStore` and return the **p90** -- the
   value 90% of past runs came in under.

Why p90 and not the average or the max?
---------------------------------------
Command runtimes are right-skewed: most runs are quick, a few are slow (cold
cache, a big migration). The *average* underestimates and would let GridGuard
start a job that then gets killed by load-shedding. The *max* is too
pessimistic -- one freak slow run would block you forever. p90 is a
conservative-but-usable middle: we plan for "a slow-ish day", not the average
day and not the worst day ever. The percentile is configurable.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from .history import HistoryStore

#: Tools whose meaning lives in their *sub*-command, not just the binary name.
_MULTI_COMMAND = {
    "git",
    "docker",
    "docker-compose",
    "npm",
    "pnpm",
    "yarn",
    "pip",
    "pip3",
    "poetry",
    "make",
    "cargo",
    "go",
    "kubectl",
    "helm",
    "terraform",
    "alembic",
    "flask",
    "django-admin",
    "python",
    "python3",
}


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (matches numpy's default method).

    ``pct`` is in ``[0, 100]``. Raises on empty input.
    """
    if not values:
        raise ValueError("percentile() requires at least one value")
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    rank = (pct / 100.0) * (len(xs) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(xs[int(rank)])
    frac = rank - lo
    return float(xs[lo] + (xs[hi] - xs[lo]) * frac)


def normalize_signature(argv: list[str]) -> str:
    """Reduce a command to a stable signature for history aggregation."""
    if not argv:
        return ""
    prog = os.path.basename(argv[0]).lower()
    if prog.endswith(".exe"):
        prog = prog[:-4]

    if prog in _MULTI_COMMAND and len(argv) > 1:
        for token in argv[1:]:
            if token.startswith("-"):
                continue  # a flag
            if "/" in token or "\\" in token or token in (".", ".."):
                continue  # path-like: probably the argument of a flag (git -C /repo)
            sub = os.path.basename(token).lower()
            return f"{prog} {sub}"
    return prog


@dataclass(frozen=True, slots=True)
class Estimate:
    seconds: float
    source: str  # "history" | "config" | "fallback" | "override"
    samples: int = 0


class DurationOracle:
    def __init__(
        self,
        history: HistoryStore,
        *,
        defaults: dict[str, float] | None = None,
        fallback_seconds: float = 120.0,
        percentile_value: float = 90.0,
        min_samples: int = 3,
    ) -> None:
        self.history = history
        self.defaults = defaults or {}
        self.fallback_seconds = float(fallback_seconds)
        self.percentile_value = float(percentile_value)
        self.min_samples = int(min_samples)

    def estimate(self, argv: list[str]) -> Estimate:
        sig = normalize_signature(argv)
        samples = self.history.durations_for(sig)
        if len(samples) >= self.min_samples:
            return Estimate(
                seconds=percentile(samples, self.percentile_value),
                source="history",
                samples=len(samples),
            )
        if sig in self.defaults:
            return Estimate(seconds=float(self.defaults[sig]), source="config")
        return Estimate(seconds=self.fallback_seconds, source="fallback")
