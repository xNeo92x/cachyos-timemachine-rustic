"""Exercise the exported interface through a real, isolated session bus."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from timemachine.core import atomic
from timemachine.gui import Window
from timemachine.service import Bridge


def test_native_service_hidden_window_and_status(configured):
    app = QApplication.instance() or QApplication([])
    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    bridge = Bridge(window)
    assert not window.isVisible() and not window.tray.isVisible()
    status = json.loads(bridge.Status())
    assert status["ok"] and status["destinations"][0]["name"] == "test"
    bridge.RequestPopup()
    assert json.loads(bridge.Status())["open_requested"] == 1
    assert json.loads(bridge.Autostart(True))["enabled"]
    assert json.loads(bridge.Status())["autostart"]
    assert not json.loads(bridge.Autostart(False))["enabled"]
    assert not json.loads(bridge.Status())["autostart"]
    assert not json.loads(bridge.Action("unknown", "test", "{}"))["ok"]
    assert not json.loads(bridge.Action("backup", "missing", "{}"))["ok"]
    assert not json.loads(bridge.Action("restore", "test", "{}"))["ok"]
    engine.config["destinations"][0]["display_name"] = "Neuer Name"
    atomic(engine.config_path, engine.config)
    assert json.loads(bridge.Status())["destinations"][0]["display_name"] == "Neuer Name"
    meta = bridge.metaObject()
    assert meta.classInfo(meta.indexOfClassInfo("D-Bus Interface")).value() == "org.cachyos.TimeMachine"
    assert meta.indexOfMethod("Autostart(bool)") >= 0
    window.timer.stop()
    window.deleteLater()
    app.processEvents()


@pytest.mark.integration
def test_session_bus_backup_browser_restore_and_autostart(tmp_path):
    binary = os.environ.get("RUSTIC_TEST_BINARY") or shutil.which("rustic")
    if not binary or not shutil.which("dbus-run-session"):
        pytest.skip("rustic and dbus-run-session required")
    script = Path(__file__).with_name("dbus_session.py")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        ["dbus-run-session", "--", sys.executable, str(script), str(tmp_path), str(Path(binary).absolute())],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 127 and "Failed to open socket: Operation not permitted" in result.stderr:
        pytest.skip("This executor does not permit session-bus sockets; CI runs the D-Bus test")
    assert result.returncode == 0, result.stdout + result.stderr
