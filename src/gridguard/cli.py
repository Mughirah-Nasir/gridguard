"""Command-line interface for GridGuard.

Subcommands::

    gridguard run [options] -- <command...>   guard and run a command
    gridguard status [--json]                 show current grid state
    gridguard schedule show [--hours N]       list upcoming cuts
    gridguard schedule import FILE [...]      CSV/JSON -> native JSON
    gridguard history [--limit N] [--json]    recent guarded runs
    gridguard serve [--host H] [--port P]     launch the web dashboard
    gridguard version

``run`` is parsed specially: everything after the first ``--`` is the command
to guard, so its own flags never clash with GridGuard's.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from . import __version__
from .config import Config, ConfigError
from .duration import DurationOracle
from .exit_codes import ExitCode
from .grid import GridOracle
from .history import HistoryStore
from .importers import load_any
from .runner import _fmt_delta, _fmt_time, guard_run
from .schedule import Schedule, ScheduleError


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return number


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive whole number")
    return number


def _load_schedule(config: Config) -> Schedule:
    if not config.schedule_path:
        raise SystemExit(
            "no schedule configured. Set 'schedule = ...' in gridguard.toml "
            "or pass --schedule."
        )
    if not config.schedule_path.is_file():
        raise SystemExit(f"schedule file not found: {config.schedule_path}")
    try:
        return Schedule.load(config.schedule_path)
    except ScheduleError as exc:
        # Prefix the offending file so multi-schedule setups stay debuggable.
        raise ScheduleError(f"{config.schedule_path}: {exc}") from exc


def _build(
    config: Config, schedule: Schedule
) -> tuple[GridOracle, DurationOracle, HistoryStore]:
    oracle = GridOracle(schedule, horizon_days=config.horizon_days)
    history = HistoryStore(config.database_path)
    duration_oracle = DurationOracle(
        history,
        defaults=config.durations,
        fallback_seconds=config.fallback_seconds,
        percentile_value=config.percentile,
        min_samples=config.min_samples,
    )
    return oracle, duration_oracle, history


def _resolve_config(args: argparse.Namespace) -> Config:
    config = Config.load(getattr(args, "config", None))
    if getattr(args, "schedule", None):
        config.schedule_path = Path(args.schedule).expanduser()
    if getattr(args, "zone", None):
        config.zone = args.zone
    return config


# --------------------------------------------------------------------------- #
# Subcommand: run
# --------------------------------------------------------------------------- #
def _split_run_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split ``run`` args into (gridguard-options, wrapped-command)."""
    if "--" not in argv:
        return argv, []
    idx = argv.index("--")
    return argv[:idx], argv[idx + 1 :]


def cmd_run(argv: list[str]) -> int:
    options, command = _split_run_args(argv)

    parser = argparse.ArgumentParser(prog="gridguard run", add_help=True)
    parser.add_argument("--config")
    parser.add_argument("--schedule")
    parser.add_argument("--zone")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="sleep until a safe window instead of exiting 87",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="decide only; never launch the command"
    )
    parser.add_argument(
        "--estimate",
        type=_positive_float,
        default=None,
        help="override the duration estimate (seconds)",
    )
    parser.add_argument(
        "--safety-factor",
        type=_positive_float,
        default=None,
        help="multiply the estimate by this safety margin",
    )
    args = parser.parse_args(options)

    if not command:
        parser.error("no command given. Usage: gridguard run [opts] -- <command>")

    config = _resolve_config(args)
    schedule = _load_schedule(config)
    oracle, duration_oracle, history = _build(config, schedule)
    safety = (
        args.safety_factor if args.safety_factor is not None else config.safety_factor
    )

    try:
        outcome = guard_run(
            command,
            oracle=oracle,
            duration_oracle=duration_oracle,
            history=history,
            tz=schedule.tz,
            safety_factor=safety,
            estimate_override=args.estimate,
            dry_run=args.dry_run,
            wait=args.wait,
        )
    except FileNotFoundError:
        print(f"error: command not found: {command[0]}", file=sys.stderr)
        history.close()
        return 127  # shell convention for "command not found"
    except PermissionError:
        print(f"error: command not executable: {command[0]}", file=sys.stderr)
        history.close()
        return 126  # shell convention for "found but not executable"

    prefix = {
        "ran": "[gridguard]",
        "would-run": "[gridguard] dry-run:",
        "blocked": "[gridguard] BLOCKED:",
    }.get(outcome.action, "[gridguard]")
    print(f"{prefix} {outcome.message}", file=sys.stderr)
    history.close()
    return outcome.exit_code


# --------------------------------------------------------------------------- #
# Subcommand: status
# --------------------------------------------------------------------------- #
def cmd_status(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gridguard status")
    parser.add_argument("--config")
    parser.add_argument("--schedule")
    parser.add_argument("--zone")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    config = _resolve_config(args)
    schedule = _load_schedule(config)
    oracle = GridOracle(schedule, horizon_days=config.horizon_days)
    now = datetime.now(schedule.tz)

    power_on = oracle.is_on(now)
    runway = oracle.runway(now)
    current = oracle.current_window(now)
    nxt = oracle.next_window_after(now)

    if args.json:
        payload = {
            "zone": schedule.zone,
            "now": now.isoformat(),
            "power_on": power_on,
            "runway_seconds": None if runway is None else runway.total_seconds(),
            "current_outage": current.to_dict() if current else None,
            "next_outage": nxt.to_dict() if nxt else None,
        }
        print(json.dumps(payload, indent=2))
        return int(ExitCode.OK)

    state = "ON" if power_on else "OUT"
    print(f"zone:    {schedule.zone}")
    print(f"now:     {now.strftime('%a %Y-%m-%d %H:%M %Z')}")
    print(f"power:   {state}")
    if power_on:
        print(f"runway:  {_fmt_delta(runway)} until next cut")
        if nxt:
            print(f"next cut: {_fmt_time(nxt.start)} ({nxt.reason})")
    elif current:
        print(f"cut ends: {_fmt_time(current.end)} ({current.reason})")
    return int(ExitCode.OK)


# --------------------------------------------------------------------------- #
# Subcommand: schedule
# --------------------------------------------------------------------------- #
def cmd_schedule(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gridguard schedule")
    sub = parser.add_subparsers(dest="action", required=True)

    show = sub.add_parser("show", help="list upcoming cuts")
    show.add_argument("--config")
    show.add_argument("--schedule")
    show.add_argument("--zone")
    show.add_argument("--hours", type=_positive_int, default=48)

    imp = sub.add_parser("import", help="convert a CSV/JSON schedule to native JSON")
    imp.add_argument("file")
    imp.add_argument("--format", choices=["csv", "json"], default=None)
    imp.add_argument("--zone", default=None)
    imp.add_argument("--timezone", default="Asia/Karachi")
    imp.add_argument("-o", "--output", default=None)

    args = parser.parse_args(argv)

    if args.action == "show":
        config = _resolve_config(args)
        schedule = _load_schedule(config)
        now = datetime.now(schedule.tz)
        window_end = now + timedelta(hours=args.hours)
        windows = [
            w
            for w in schedule.merged(now.date(), window_end.date())
            if w.end > now and w.start < window_end
        ]
        print(f"upcoming cuts for {schedule.zone} (next {args.hours}h):")
        if not windows:
            print("  (none scheduled)")
        for w in windows:
            print(
                f"  {w.start.strftime('%a %m-%d %H:%M')} -> "
                f"{w.end.strftime('%H:%M')}  ({_fmt_delta(w.duration)})  {w.reason}"
            )
        return int(ExitCode.OK)

    # import
    try:
        schedule = load_any(
            args.file, fmt=args.format, zone=args.zone, timezone=args.timezone
        )
    except ScheduleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE)

    text = schedule.to_json()
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return int(ExitCode.OK)


# --------------------------------------------------------------------------- #
# Subcommand: history
# --------------------------------------------------------------------------- #
def cmd_history(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gridguard history")
    parser.add_argument("--config")
    parser.add_argument("--limit", type=_positive_int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    config = Config.load(getattr(args, "config", None))
    history = HistoryStore(config.database_path)
    rows = history.recent(args.limit)
    history.close()

    if args.json:
        print(json.dumps(rows, indent=2))
        return int(ExitCode.OK)

    if not rows:
        print("no runs recorded yet.")
        return int(ExitCode.OK)

    print(f"{'when':<20} {'dur':>8}  {'code':>4}  command")
    for r in rows:
        when = r["started_at"][:19].replace("T", " ")
        dur = _fmt_delta(timedelta(seconds=r["duration_s"]))
        print(f"{when:<20} {dur:>8}  {r['exit_code']:>4}  {r['raw_command']}")
    return int(ExitCode.OK)


# --------------------------------------------------------------------------- #
# Subcommand: serve
# --------------------------------------------------------------------------- #
def cmd_serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gridguard serve")
    parser.add_argument("--config")
    parser.add_argument("--schedule")
    parser.add_argument("--zone")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8087)
    args = parser.parse_args(argv)

    config = _resolve_config(args)
    _load_schedule(config)  # validate early with a friendly error

    try:
        import uvicorn  # noqa: F401

        from .dashboard.app import create_app
    except ImportError:
        print(
            "the dashboard needs extra packages. Install with:\n"
            "  pip install 'gridguard[dashboard]'",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    app = create_app(config)
    print(f"GridGuard dashboard on http://{args.host}:{args.port}", file=sys.stderr)
    print(
        "note: the dashboard is for local use only -- do not expose it on "
        "public networks (see SECURITY.md).",
        file=sys.stderr,
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return int(ExitCode.OK)


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
_COMMANDS = {
    "run": cmd_run,
    "status": cmd_status,
    "schedule": cmd_schedule,
    "history": cmd_history,
    "serve": cmd_serve,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _print_usage()
        return int(ExitCode.OK) if argv else int(ExitCode.USAGE)
    if argv[0] in ("version", "--version", "-V"):
        print(f"gridguard {__version__}")
        return int(ExitCode.OK)

    cmd, rest = argv[0], argv[1:]
    handler = _COMMANDS.get(cmd)
    if handler is None:
        print(f"unknown command: {cmd}\n", file=sys.stderr)
        _print_usage()
        return int(ExitCode.USAGE)
    try:
        return handler(rest)
    except BrokenPipeError:
        # Output was piped to e.g. `head` which closed early. Not an error.
        import os

        try:
            sys.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        os._exit(int(ExitCode.OK))
    except SystemExit as exc:  # argparse error / our friendly raises
        if isinstance(exc.code, str):
            print(f"error: {exc.code}", file=sys.stderr)
            return int(ExitCode.USAGE)
        return int(exc.code) if exc.code is not None else int(ExitCode.OK)
    except (ScheduleError, ConfigError, ZoneInfoNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE)
    except sqlite3.OperationalError as exc:
        print(f"error: cannot open history database: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE)


def _print_usage() -> None:
    print(
        "gridguard -- guard commands against load-shedding\n\n"
        "usage:\n"
        "  gridguard run [opts] -- <command...>   guard and run a command\n"
        "  gridguard status [--json]              current grid state\n"
        "  gridguard schedule show [--hours N]    upcoming cuts\n"
        "  gridguard schedule import FILE [...]   CSV/JSON -> native JSON\n"
        "  gridguard history [--limit N] [--json] recent guarded runs\n"
        "  gridguard serve [--host --port]        web dashboard\n"
        "  gridguard version\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
