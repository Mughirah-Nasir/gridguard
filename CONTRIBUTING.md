# Contributing to GridGuard

Thanks for looking at the project! GridGuard is small on purpose, and
contributions are welcome as long as they keep it small, honest and tested.

## Set up a development environment

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows PowerShell

python -m pip install -U pip
pip install -e ".[dashboard,dev]"
```

Python 3.10, 3.11 and 3.12 are supported (3.10 uses the `tomli` backport
for TOML parsing; this is installed automatically).

## Before you open a pull request

All three of these must pass locally -- CI runs the same commands:

```bash
python -m ruff check .
python -m pytest -v
python -m build
```

## Adding code

* New behaviour needs a test. Bug fixes should add the test that *would
  have caught* the bug -- the existing suite has two examples of exactly
  that (see `AUTHENTICITY.md`).
* The core (`src/gridguard/`, minus `dashboard/`) is standard-library only.
  Please don't add runtime dependencies to it; the dashboard's dependencies
  live behind the `[dashboard]` extra.
* The decision logic (`plan_guard`) is a pure function and the executor
  takes injectable `now_fn` / `sleep_fn` / `runner` callables. Tests should
  use those hooks instead of sleeping or spawning real processes.
* User-facing mistakes (bad flags, missing files, malformed schedules) must
  produce a one-line `error: ...` message and exit code 2 -- never a
  traceback. There are tests for this in `tests/test_cli_errors.py`.

## Keeping the docs honest

This repository deliberately avoids inflated claims:

* If you change the number of tests, update the README badge and text to
  the **actual** `pytest` count.
* Don't describe features that don't exist or aren't finished. Limitations
  belong in the README's "Known limits" section, stated plainly.
* Performance numbers are machine-dependent; the benchmark prints its own
  disclaimer and we don't copy its output into the docs as a promise.

## Commit style

Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `chore:`)
with a short imperative summary. Small commits that do one thing are easier
to review than one big one.
