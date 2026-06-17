# Authenticity — the interview defense map

This file maps every defensible decision in GridGuard to where it lives in
the code and the one-line reason behind it. If you (recruiter, interviewer,
future me) want to test whether the author understands this project, ask
about any row.

| Decision | Where | Why |
|---|---|---|
| Exit code **87** for "grid-blocked" | `exit_codes.py` | Callers must distinguish *guard refused* from *command failed*; 87 avoids the 0/1/2/125–128/128+sig ranges common tools use. |
| **p90** duration estimate, not mean/max | `duration.py` | Runtimes are right-skewed; mean gets builds killed mid-cut, max is hostage to one freak run. p90 plans for a slow-ish day. |
| × **safety factor** (default 1.25) on top of p90 | `runner.py`, `config.py` | Estimate error is asymmetric: starting 5 min early costs nothing, finishing 5 min late loses the whole job. |
| **Failed runs excluded** from history | `history.py::durations_for` | A build that crashed in 3 s must not teach the oracle that builds are fast. |
| Command **signature normalisation** (`docker build -t app .` → `docker build`) | `duration.py::normalize_signature` | Per-exact-argv history would never accumulate samples; per-binary is too coarse for multi-command tools. |
| Skip **path-like tokens** in normalisation | same | `git -C /repo status` must map to `git status`, not `git repo` — found by a failing test during development. |
| **Pure** `plan_guard()` decision core | `runner.py` | Deterministic, no clock/subprocess → the whole decision matrix unit-tests in milliseconds. |
| **Injectable** `now_fn` / `sleep_fn` / `runner` | `runner.py::guard_run` | Wait-mode tests simulate hours in microseconds; no test ever launches a real process. |
| Half-open **[start, end)** outage windows | `schedule.py::OutageWindow` | Cut ending 16:00 = power back *at* 16:00; kills boundary off-by-ones, asserted in tests. |
| **Merge** adjacent/overlapping windows before runway math | `schedule.py::merged` | Back-to-back cuts must not show a fake instant of power between them. |
| `expand()` looks **one day back**, then filters | `schedule.py::expand` | Catches 23:00→02:00 windows crossing into today; the filter fixes a real bug where *all* of yesterday's windows leaked in. |
| **Saw-tooth** candidate search in `next_safe_start` | `grid.py` | Runway only jumps up at window-ends; test "now + each window end" instead of scanning minute-by-minute. |
| Schedule models **outages, not uptime** | `schedule.py` | That is the shape IESCO/LESCO/K-Electric actually publish; authoring stays human. |
| Runway `None` = unlimited vs `timedelta(0)` = off now | `grid.py::runway` | Three states (off / finite / no cut in horizon) collapse safely into "can I fit `needed`?" |
| **SQLite via stdlib**, no ORM | `history.py` | One table, one file, zero deps — a guard should be lighter than the jobs it guards. |
| Dashboard as **optional extra** `[dashboard]` | `pyproject.toml`, lazy import in `cli.py::cmd_serve` | Core stays zero-dependency; FastAPI only loads if you ask for it. |
| `--` **separator** splits guard flags from the wrapped command | `cli.py::_split_run_args` | The wrapped command's own flags must never collide with GridGuard's. |
| **TOML config via `tomllib`** (3.11+) | `config.py` | Config without adding a dependency; the version floor is a deliberate trade. |
| `BrokenPipeError` handled in `main()` | `cli.py` | `gridguard ... \| head` must not stack-trace; found during live smoke-testing. |
| CSV importer with row-level errors | `importers.py` | Rotas circulate as tables/WhatsApp forwards, not JSON; errors name the offending row. |

## Bugs found & fixed during this build (the proof it was *developed*)

1. **Stale previous-day window leak.** `Schedule.expand()` iterated from
   `start − 1 day` to catch midnight-crossing cuts but returned *every*
   window from that previous day, so yesterday's 14:00–16:00 cut appeared in
   today's listing. Caught by `test_expand_basic_window` and friends; fixed
   with an overlap filter (`end > range_start`). Commit: *fix(schedule):
   filter stale previous-day windows out of expand()*.
2. **Signature normaliser vs flag arguments.** `git -C /repo status`
   normalised to `git repo` because `/repo` (the argument *of* `-C`) was
   taken as the subcommand. Caught by the parametrised
   `test_normalize_signature` table; fixed by skipping path-like tokens.
   Commit: *fix(duration): skip path-like tokens when extracting
   subcommand*.

Both failures are visible in the test names; the fixes are small,
explainable, and would be easy to whiteboard.

## AI assistance, plainly

Designed and directed by Mughirah Nasir; implemented in disclosed
pair-programming sessions with Claude (Anthropic). See `PROVENANCE.md` for
the verification chain (git authorship → GitHub push timestamp → SHA-256
manifest in `CERTIFICATE.html` → optional OpenTimestamps anchor).
