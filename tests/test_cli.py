"""End-to-end-ish tests for the CLI via main()."""

from __future__ import annotations

import json

from gridguard.cli import main

_EMPTY = '{"version":1,"zone":"EMPTY","timezone":"Asia/Karachi","recurring":[]}'
# Two adjacent windows that merge to cover the entire day -> always "off".
_ALWAYS_OFF = (
    '{"version":1,"zone":"OFF","timezone":"Asia/Karachi","recurring":['
    '{"days":"daily","start":"00:00","end":"12:00"},'
    '{"days":"daily","start":"12:00","end":"00:00"}]}'
)
_CSV = "type,days,date,start,end,reason\nrecurring,daily,,02:00,04:00,load-shedding\n"


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _toml_path(path):
    # TOML basic strings treat backslashes as escapes, so Windows paths like
    # C:\Users\... must be written with forward slashes in test configs.
    return path.as_posix()


def _config(tmp_path):
    db = tmp_path / "history.db"
    cfg = tmp_path / "gridguard.toml"
    cfg.write_text(f'zone = "T"\ndatabase = "{_toml_path(db)}"\n', encoding="utf-8")
    return str(cfg)


def test_version(capsys):
    assert main(["version"]) == 0
    assert "gridguard" in capsys.readouterr().out


def test_unknown_command():
    assert main(["frobnicate"]) == 2


def test_status_json(tmp_path, capsys):
    sched = _write(tmp_path, "empty.json", _EMPTY)
    rc = main(["status", "--schedule", sched, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["zone"] == "EMPTY"
    assert payload["power_on"] is True
    assert payload["runway_seconds"] is None  # no cuts -> unlimited


def test_schedule_show(tmp_path, capsys):
    sched = _write(tmp_path, "empty.json", _EMPTY)
    rc = main(["schedule", "show", "--schedule", sched, "--hours", "24"])
    assert rc == 0
    assert "upcoming cuts" in capsys.readouterr().out


def test_schedule_import_csv(tmp_path, capsys):
    csv_path = _write(tmp_path, "s.csv", _CSV)
    rc = main(["schedule", "import", csv_path, "--format", "csv", "--zone", "Z2"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["zone"] == "Z2"
    assert len(out["recurring"]) == 1


def test_history_json_empty(tmp_path, capsys):
    cfg = _config(tmp_path)
    rc = main(["history", "--config", cfg, "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_run_dry_run_go(tmp_path):
    sched = _write(tmp_path, "empty.json", _EMPTY)
    cfg = _config(tmp_path)
    rc = main(
        [
            "run",
            "--config",
            cfg,
            "--schedule",
            sched,
            "--dry-run",
            "--estimate",
            "60",
            "--",
            "echo",
            "hi",
        ]
    )
    assert rc == 0  # unlimited runway -> would run


def test_run_blocked_returns_87(tmp_path):
    sched = _write(tmp_path, "off.json", _ALWAYS_OFF)
    cfg = _config(tmp_path)
    rc = main(
        [
            "run",
            "--config",
            cfg,
            "--schedule",
            sched,
            "--estimate",
            "60",
            "--",
            "echo",
            "hi",
        ]
    )
    assert rc == 87  # power always out -> blocked


def test_run_requires_command(tmp_path):
    sched = _write(tmp_path, "empty.json", _EMPTY)
    rc = main(["run", "--schedule", sched])  # no `-- command`
    assert rc == 2
