"""Error-path and input-validation tests for the CLI.

Every normal user mistake must produce a clean ``error: ...`` message and
exit code 2 -- never a Python traceback. A missing wrapped command uses the
shell conventions 127 (not found) / 126 (not executable).
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from gridguard.cli import main
from gridguard.grid import GridOracle
from gridguard.schedule import Schedule

_GOOD = '{"version":1,"zone":"OK","timezone":"Asia/Karachi","recurring":[]}'


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _toml_path(path):
    # TOML basic strings treat backslashes as escapes, so Windows paths like
    # C:\Users\... must be written with forward slashes in test configs.
    return path.as_posix()


# --- config errors ----------------------------------------------------------
def test_missing_config_file(tmp_path, capsys):
    rc = main(["status", "--config", str(tmp_path / "missing.toml")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error: config file not found" in err
    assert "Traceback" not in err


def test_invalid_toml_config(tmp_path, capsys):
    cfg = _write(tmp_path, "bad.toml", "zone = [unclosed\n")
    rc = main(["status", "--config", cfg])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error: invalid TOML" in err
    assert "Traceback" not in err


# --- schedule errors --------------------------------------------------------
def test_bad_schedule_json(tmp_path, capsys):
    sched = _write(tmp_path, "bad.json", "{not json at all")
    rc = main(["status", "--schedule", sched])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err
    assert "invalid JSON" in err
    assert "bad.json" in err  # the offending file is named
    assert "Traceback" not in err


def test_schedule_file_not_found(tmp_path, capsys):
    rc = main(["status", "--schedule", str(tmp_path / "nope.json")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error: schedule file not found" in err


def test_invalid_timezone_in_schedule(tmp_path, capsys):
    sched = _write(
        tmp_path,
        "tz.json",
        '{"version":1,"zone":"Z","timezone":"Mars/Olympus","recurring":[]}',
    )
    rc = main(["status", "--schedule", sched])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err
    assert "Traceback" not in err


# --- flag validation --------------------------------------------------------
def test_negative_estimate_rejected(tmp_path, capsys):
    sched = _write(tmp_path, "s.json", _GOOD)
    rc = main(["run", "--schedule", sched, "--estimate", "-5", "--", "echo", "x"])
    assert rc == 2
    assert "must be a positive number" in capsys.readouterr().err


def test_zero_estimate_rejected(tmp_path, capsys):
    sched = _write(tmp_path, "s.json", _GOOD)
    rc = main(["run", "--schedule", sched, "--estimate", "0", "--", "echo", "x"])
    assert rc == 2


def test_negative_safety_factor_rejected(tmp_path, capsys):
    sched = _write(tmp_path, "s.json", _GOOD)
    rc = main(["run", "--schedule", sched, "--safety-factor", "-1", "--", "echo", "x"])
    assert rc == 2
    assert "must be a positive number" in capsys.readouterr().err


def test_negative_hours_rejected(tmp_path, capsys):
    sched = _write(tmp_path, "s.json", _GOOD)
    rc = main(["schedule", "show", "--schedule", sched, "--hours", "-4"])
    assert rc == 2
    assert "must be a positive whole number" in capsys.readouterr().err


def test_negative_history_limit_rejected(tmp_path, capsys):
    cfg = _write(tmp_path, "c.toml", f'database = "{_toml_path(tmp_path / "h.db")}"\n')
    rc = main(["history", "--config", cfg, "--limit", "-1"])
    assert rc == 2


# --- wrapped-command errors -------------------------------------------------
def test_command_not_found_exits_127(tmp_path, capsys):
    sched = _write(tmp_path, "s.json", _GOOD)
    cfg = _write(tmp_path, "c.toml", f'database = "{_toml_path(tmp_path / "h.db")}"\n')
    rc = main(
        [
            "run",
            "--config",
            cfg,
            "--schedule",
            sched,
            "--estimate",
            "1",
            "--",
            "definitely-not-a-real-binary-xyz",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 127
    assert "error: command not found" in err
    assert "Traceback" not in err


# --- database errors --------------------------------------------------------
def test_unwritable_database_path(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    cfg = _write(
        tmp_path, "c.toml", f'database = "{_toml_path(blocker / "history.db")}"\n'
    )
    rc = main(["history", "--config", cfg])
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err
    assert "Traceback" not in err


# --- timezone handling ------------------------------------------------------
def test_schedule_in_other_timezone():
    s = Schedule.from_dict(
        {
            "version": 1,
            "zone": "IN",
            "timezone": "Asia/Kolkata",
            "recurring": [{"days": "daily", "start": "14:00", "end": "16:00"}],
        }
    )
    kolkata = ZoneInfo("Asia/Kolkata")
    inside = datetime(2026, 6, 16, 14, 30, tzinfo=kolkata)
    outside = datetime(2026, 6, 16, 16, 30, tzinfo=kolkata)
    oracle = GridOracle(s)
    assert oracle.is_off(inside)
    assert not oracle.is_off(outside)
    # A Karachi clock (-30 min) asking about the same instants must agree.
    karachi = ZoneInfo("Asia/Karachi")
    assert oracle.is_off(inside.astimezone(karachi))
    assert not oracle.is_off(outside.astimezone(karachi))


# --- manual schedule end-to-end --------------------------------------------
def test_status_on_bundled_example(capsys):
    rc = main(["status", "--schedule", "examples/iesco-f7.json", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["zone"] == "IESCO-F7-1"
    assert isinstance(payload["power_on"], bool)
    assert "runway_seconds" in payload
