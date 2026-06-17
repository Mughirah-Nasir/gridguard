# Changelog

All notable changes to GridGuard are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) loosely; versions follow
[SemVer](https://semver.org/).

## v1.0.0 — Initial public release

- Added outage-aware command guard (`gridguard run -- <command>`) with the
  reserved exit code 87 for "blocked by the grid"
- Added manual outage schedule support (JSON format, plus a CSV importer)
- Added duration estimation from local run history (p90 of past successful
  runs, with config defaults and a global fallback)
- Added CLI: `run`, `status`, `schedule show`, `schedule import`, `history`,
  `serve`, `version`
- Added friendly CLI error handling: one-line `error: ...` messages and exit
  code 2 for user/config mistakes, 127/126 for missing/unexecutable commands
- Added local FastAPI dashboard (optional `[dashboard]` extra, localhost by
  default, no authentication -- local use only)
- Added test suite and a small decision-core benchmark
  (`python -m benchmark.run_scenarios`)
- Added CI (ruff + pytest + build on Python 3.10/3.11/3.12)
- Added provenance/authenticity documentation and security policy
- Documented limitations honestly: schedules are entered manually, no outage
  prediction, no PDF import, estimates are per-command-signature
