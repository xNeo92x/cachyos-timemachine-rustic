"""Subprocess probe; never touches the real desktop or its configuration."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusMessage

from timemachine.core import Engine, atomic
from timemachine.integration import OBJECT, SERVICE


def main():
    base = Path(sys.argv[1])
    os.environ.update(
        XDG_CONFIG_HOME=str(base / "config-base"),
        XDG_STATE_HOME=str(base / "state-base"),
        XDG_CACHE_HOME=str(base / "cache"),
    )
    source = base / "source"
    source.mkdir()
    (source / "file.txt").write_text("DBus restore content")
    atomic(
        base / "config/config.json",
        {
            "source": str(source),
            "rustic_binary": sys.argv[2],
            "destinations": [{"name": "test", "repository": str(base / "repo")}],
        },
    )
    engine = Engine(base / "config", base / "state")
    engine.set_key("test", "test-password")
    engine.initialize("test")
    app = QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    daemon = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "timemachine.cli",
            "--config-dir",
            str(base / "config"),
            "--state-dir",
            str(base / "state"),
            "service",
        ],
        cwd=Path(__file__).resolve().parent.parent,
    )

    def call(member, *args):
        message = QDBusMessage.createMethodCall(SERVICE, OBJECT, SERVICE, member)
        message.setArguments(list(args))
        reply = bus.call(message, timeout=3000)
        assert reply.type() != QDBusMessage.MessageType.ErrorMessage, reply.errorMessage()
        app.processEvents()
        return json.loads(reply.arguments()[0])

    def action(command, **options):
        answer = call("Action", command, "test", json.dumps(options))
        assert answer["ok"], answer
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = call("Result", answer["request"])
            if result.get("done"):
                assert result["result"]["ok"], result
                return result["result"]
            time.sleep(0.02)
        raise AssertionError("Operation did not finish")

    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if daemon.poll() is not None:
                raise AssertionError("Service exited early")
            if bus.interface().isServiceRegistered(SERVICE).value():
                try:
                    call("Status")
                    break
                except AssertionError:
                    pass
            time.sleep(0.02)
        status = call("Status")
        assert status["ok"] and len(status["destinations"]) == 1
        assert call("RequestPopup")["ok"]
        assert call("Status")["open_requested"] == 1
        assert call("Autostart", True)["enabled"]
        assert call("Status")["autostart"]
        assert not call("Autostart", False)["enabled"]
        assert not call("Status")["autostart"]
        assert not call("Action", "unknown", "test", "{}")["ok"]
        assert not call("Action", "backup", "missing", "{}")["ok"]
        assert not call("Action", "restore", "test", "{}")["ok"]
        action("backup")
        snapshot = action("snapshots")["snapshots"][0]["id"]
        entries = action("ls", snapshot=snapshot, path=str(source))["entries"]
        assert entries[0]["name"] == "file.txt"
        result = action(
            "restore", snapshot=snapshot, path=str(source / "file.txt"), target=str(base / "restored")
        )
        assert Path(result["restored"]).read_text() == "DBus restore content"
        assert (source / "file.txt").read_text() == "DBus restore content"
        assert call("Shutdown")["ok"]
        daemon.wait(timeout=5)
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            daemon.wait(timeout=5)


if __name__ == "__main__":
    main()
