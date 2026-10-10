"""Live byte progress from rustic's native protocol through the shared UI."""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

from timemachine import progress
from timemachine.core import atomic
from timemachine.gui import Window
from timemachine.i18n import configure
from timemachine.service import Bridge


@pytest.fixture
def clock(monkeypatch):
    stamp = [100.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: stamp[0])
    monkeypatch.setattr(progress.time, "time", lambda: stamp[0] + 1000)
    return stamp


def test_unknown_size_then_total_rate_and_summary(clock):
    tracker = progress.ProgressTracker()
    clock[0] += 1
    first = tracker.feed({"message_type": "status", "bytes_done": 1024, "seconds_elapsed": 1})
    assert first["bytes_per_second"] == 1024
    assert "percent_done" not in first and "total_bytes" not in first
    clock[0] += 1
    second = tracker.feed({"message_type": "status", "bytes_done": 4096, "total_bytes": 8192,
                           "seconds_elapsed": 2, "seconds_remaining": 2})
    assert second["percent_done"] == 0.5
    assert second["bytes_per_second"] == 2048
    assert tracker.feed({"message_type": "error", "message": "problem"}) is None
    assert tracker.value == second
    clock[0] += 1
    summary = tracker.feed({"message_type": "summary", "total_bytes_processed": 8192,
                            "total_duration": 3.25, "snapshot_id": "a0" * 32})
    assert summary["snapshot_id"] == "a0" * 32
    assert summary["bytes_done"] == summary["total_bytes"] == 8192
    assert summary["seconds_elapsed"] == 3.25 and summary["percent_done"] == 1


def test_new_byte_phase_resets_rate_and_total(clock):
    tracker = progress.ProgressTracker()
    clock[0] += 1
    tracker.feed({"message_type": "status", "bytes_done": 10000, "total_bytes": 10000, "percent_done": 1})
    clock[0] += 1
    reset = tracker.feed({"message_type": "status", "bytes_done": 0, "seconds_elapsed": 0})
    assert "total_bytes" not in reset and "percent_done" not in reset
    assert reset["bytes_per_second"] is None
    clock[0] += 1
    assert tracker.feed({"message_type": "status", "bytes_done": 100})["bytes_per_second"] == 100


def test_protocol_metadata_does_not_persist_strings_or_invalid_numbers(clock):
    tracker = progress.ProgressTracker()
    event = tracker.feed({"message_type": "status", "bytes_done": 10, "total_bytes": True,
                          "seconds_remaining": -1, "percent_done": float("nan"),
                          "bytes_per_second": "untrusted", "message": "secret", "snapshot_id": "secret"})
    assert "message" not in event and "snapshot_id" not in event
    assert "total_bytes" not in event and "percent_done" not in event and "seconds_remaining" not in event
    json.dumps(event, allow_nan=False)


def row():
    return {"status": "running", "phase": "backup", "started_at": dt.datetime.fromtimestamp(1000, dt.timezone.utc).isoformat(),
            "progress": {"bytes_done": 1024 ** 2, "total_bytes": 2 * 1024 ** 2, "percent_done": 0.5,
                         "bytes_per_second": 1024 ** 2, "seconds_remaining": 10, "updated_at_epoch": 1010}}


@pytest.mark.parametrize("language,detail,speed,timing", [
    ("de", "50,0 % · Verarbeitet: 1.0 MiB / 2.0 MiB", "Verarbeitung: 1.0 MiB/s", "Verstrichen: 00:00:11 · Verbleibend: ca. 00:00:10"),
    ("en", "50.0 % · Processed: 1.0 MiB / 2.0 MiB", "Processing: 1.0 MiB/s", "Elapsed: 00:00:11 · Remaining: about 00:00:10"),
])
def test_live_view_is_localized_and_stale_speed_eta_disappear(language, detail, speed, timing):
    configure(language)
    view = progress.progress_view(row(), now_epoch=1011)
    assert view["active"] and view["percent"] == 0.5
    assert (view["detail"], view["speed"], view["timing"]) == (detail, speed, timing)
    stale = progress.progress_view(row(), now_epoch=1015)
    assert stale["detail"] == detail and stale["speed"].endswith("–")
    assert stale["timing"].endswith("00:00:15")
    unknown = row()
    del unknown["progress"]["total_bytes"]
    del unknown["progress"]["percent_done"]
    view = progress.progress_view(unknown, now_epoch=1011)
    assert view["percent"] is None and "1.0 MiB" in view["detail"] and view["speed"] == speed
    unknown["phase"] = "retention"
    assert not progress.progress_view(unknown)["active"]
    unknown["status"] = "idle"
    assert not progress.progress_view(unknown)["active"]


def test_qt_and_dbus_export_same_live_metrics(configured):
    app = QApplication.instance() or QApplication([])
    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    try:
        with engine.operation("test", "backup"):
            data = row()["progress"]
            data["updated_at_epoch"] = time.time()
            engine.update("test", progress=data)
            window.refresh()
            exported = json.loads(Bridge(window).Status())["destinations"][0]["progress_view"]
            assert exported["active"] and exported["percent"] == 0.5
            assert "50,0 %" in window.progress_details.text()
            assert exported["speed"] in window.progress_details.text()
            assert "1.0 MiB/s" in exported["speed"]
            assert window.progress.maximum() == 1000 and window.progress.value() == 500
        window.refresh()
        assert window.progress.isHidden() and window.progress_details.isHidden()
    finally:
        window.timer.stop()
        window.deleteLater()
        app.processEvents()


@pytest.mark.integration
def test_real_backup_reports_progress_before_finishing_even_with_numeric_password(configured):
    engine, source, _ = configured
    binary = os.environ.get("RUSTIC_TEST_BINARY") or shutil.which("rustic")
    if not binary:
        pytest.skip("rustic binary required")
    atomic(engine.password_path(engine.dest("test")), "0\n")
    engine.config["rustic_binary"] = binary
    atomic(engine.config_path, engine.config)
    # Unique, incompressible data and one CPU ensure multiple native progress
    # events on fast CI hosts; neither counters nor rustic output are simulated.
    for index in range(6):
        (source / f"large-{index}.bin").write_bytes(os.urandom(32 * 1024 ** 2))
    command = [sys.executable, "-c", "import os; from timemachine.cli import main; os.sched_setaffinity(0, {min(os.sched_getaffinity(0))}); main()",
               "--config-dir", str(engine.config_dir), "--state-dir", str(engine.state_dir), "backup", "--dest", "test", "--json"]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    observed = []
    deadline = time.monotonic() + 60
    try:
        while process.poll() is None and time.monotonic() < deadline:
            state = engine.state("test")
            event = state.get("progress", {})
            if state.get("status") == "running" and event.get("message_type") == "status" and 0 < event.get("percent_done", 0) < 1:
                observed.append(event)
            time.sleep(0.05)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stdout + stderr + engine.logs("test")
        assert json.loads(stdout)["ok"]
        assert any(event["bytes_done"] > 0 and event["total_bytes"] > 0 and event["bytes_per_second"] > 0 for event in observed), observed
        final = engine.state("test")
        assert final["last_success"] and final["progress"]["percent_done"] == 1
        assert final["progress"]["snapshot_id"] == engine.snapshots("test")[0]["id"]
        assert final["progress"]["bytes_done"] >= 192 * 1024 ** 2
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
