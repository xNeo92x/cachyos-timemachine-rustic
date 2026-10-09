import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from timemachine.core import APP, Engine, Error, atomic, safe_path, safe_snapshot, validate


@pytest.mark.parametrize("value", ["../bad", "-bad", "a/b", "", "name\nOther=yes"])
def test_reject_unsafe_names(value):
    with pytest.raises(Error):
        validate({"destinations": [{"name": value, "repository": "/repo"}]})


@pytest.mark.parametrize("value", ["../file", "/home/../file", "relative", "/bad\0file"])
def test_reject_unsafe_paths(value):
    with pytest.raises(Error):
        safe_path(value)


def test_snapshot_ids_are_not_command_options():
    with pytest.raises(Error):
        safe_snapshot("--delete")
    assert safe_snapshot("a" * 64) == "a" * 64


def test_secret_permissions_and_no_replacement(configured):
    engine, _, _ = configured
    key = engine.password_path(engine.dest("test"))
    assert key.stat().st_mode & 0o777 == 0o600
    with pytest.raises(Error, match="existiert"):
        engine.set_key("test", "replacement")
    assert engine.show_key("test") == "test-only-password"


def test_missing_source_keeps_last_success_and_skips_retention(configured):
    engine, source, _ = configured
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    engine.update("test", last_success=stamp)
    engine.config["source"] = [str(source), "/this-source-does-not-exist"]
    with pytest.raises(Error, match="Quelle fehlt"):
        engine.backup("test")
    state = engine.state("test")
    assert state["last_success"] == stamp
    assert state["last_backup_status"] == "failed"


def test_stale_and_crash_status(configured):
    engine, _, _ = configured
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()
    engine.update("test", last_success=old, status="running", pid=999999999, proc_start="1")
    row = engine.status()[0]
    assert row["stale"]
    assert row["status"] == "interrupted"


def test_lock_rejects_concurrent_writer(configured):
    engine, _, _ = configured
    second = Engine(engine.config_dir, engine.state_dir)
    with engine.operation("test", "backup"):
        with pytest.raises(Error, match="bereits"):
            with second.operation("test", "restore"):
                pass
        assert engine.state("test")["status"] == "running"


def test_timer_generation_and_pause_do_not_require_service(configured, monkeypatch):
    engine, _, _ = configured
    engine.config["destinations"][0]["schedule"] = "*-*-* 03:00:00"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    engine.install_timers()
    unit_dir = Path(os.environ["XDG_CONFIG_HOME"]) / "systemd/user"
    timer = (unit_dir / (APP + "-test.timer")).read_text()
    service = (unit_dir / (APP + "-test.service")).read_text()
    assert "Persistent=true" in timer
    assert "Requires=" not in timer
    assert "--dest" in service
    assert "configuration with spaces" in service
    assert "TimeoutStartSec=infinity" in service
    engine.install_timers(False)
    assert any(c[2] == "disable" for c in calls if c[0] == "systemctl" and len(c) > 2)


@pytest.mark.integration
def test_backup_history_browse_restore_and_check(rustic_engine, tmp_path):
    engine, source, _ = rustic_engine
    engine.backup("test")
    first = engine.snapshots("test")[0]
    assert engine.state("test")["last_success"]
    entries = engine.ls("test", first["id"], str(source))
    assert {n["name"] for n in entries} == {"file.txt", "subdir"}
    assert next(n for n in entries if n["name"] == "subdir")["type"] == "dir"
    (source / "file.txt").write_text("second version\n")
    engine.backup("test")
    assert len(engine.snapshots("test")) == 2
    result = engine.restore("test", first["id"], str(source / "file.txt"), tmp_path / "restore")
    assert Path(result["restored"]).read_text() == "first version\n"
    assert (source / "file.txt").read_text() == "second version\n"
    # Unicode file names, folders and repeated restores must all work.
    folder = engine.restore("test", first["id"], str(source / "subdir"), tmp_path / "restore")
    assert (Path(folder["restored"]) / "üñïcode 🕒.txt").read_text() == "nested\n"
    repeated = engine.restore("test", first["id"], str(source / "file.txt"), tmp_path / "restore")
    assert repeated["target"] != result["target"]
    engine.check("test")
    assert engine.state("test")["last_check"]


@pytest.mark.integration
def test_dry_run_writes_no_snapshot_and_runs_no_hook(rustic_engine, tmp_path):
    engine, _, _ = rustic_engine
    marker = tmp_path / "hook-ran"
    engine.config["destinations"][0]["pre_command"] = "touch '" + str(marker) + "'"
    engine.backup("test", dry_run=True)
    assert not marker.exists()
    assert not engine.snapshots("test")
    assert "last_success" not in engine.state("test")


@pytest.mark.integration
def test_excludes_nested_repository_keys_and_state(rustic_engine):
    engine, source, _ = rustic_engine
    nested_repo = source / "backup-repo"
    engine.config["destinations"][0]["repository"] = str(nested_repo)
    engine.config["source"] = [str(source), str(engine.config_dir), str(engine.state_dir)]
    atomic(engine.config_dir / "excludes.txt", "!subdir/\n")
    engine.initialize("test")
    engine.backup("test")
    snap = engine.snapshots("test")[0]
    entries = engine.ls("test", snap["id"], str(source))
    assert {n["name"] for n in entries} == {"file.txt"}
    config_entries = engine.ls("test", snap["id"], str(engine.config_dir))
    assert "keys" not in {n["name"] for n in config_entries}


@pytest.mark.integration
def test_wrong_password_marks_failed_without_losing_previous_success(rustic_engine):
    engine, _, _ = rustic_engine
    engine.backup("test")
    previous = engine.state("test")["last_success"]
    atomic(engine.password_path(engine.dest("test")), "wrong-password\n")
    with pytest.raises(Error):
        engine.backup("test")
    assert engine.state("test")["last_success"] == previous
    assert engine.state("test")["last_backup_status"] == "failed"


def test_cli_cancellation_terminates_hook_process_group(configured, tmp_path):
    engine, _, _ = configured
    config = engine.config
    config["destinations"][0]["pre_command"] = "sleep 60"
    atomic(engine.config_path, config)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "timemachine.cli",
            "--config-dir",
            str(engine.config_dir),
            "--state-dir",
            str(engine.state_dir),
            "backup",
            "--dest",
            "test",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(100):
            if engine.state("test").get("status") == "running":
                break
            time.sleep(0.02)
        engine.cancel("test")
        stdout, _ = process.communicate(timeout=8)
        assert process.returncode == 1
        assert not json.loads(stdout)["ok"]
        assert engine.state("test")["status"] == "cancelled"
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGKILL)
            process.wait()
