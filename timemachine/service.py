"""Session D-Bus bridge. Repository commands run in isolated CLI subprocesses."""

import json
import sys
import uuid

from PySide6.QtCore import ClassInfo, QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage
from PySide6.QtWidgets import QApplication

from .core import Engine, Error
from .gui import Window, date, human_size, status_text
from .integration import OBJECT, SERVICE, autostart_enabled, integrate_panel, set_autostart


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


@ClassInfo(**{"D-Bus Interface": SERVICE})
class Bridge(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.results = {}
        self.open_requested = 0

    @Slot(result=str)
    def Status(self):
        try:
            self.window.engine = Engine(self.window.config_dir, self.window.state_dir)
            self.window.refresh()
            rows = []
            for row in self.window.rows:
                item = dict(row)
                item.update(
                    status_text=status_text(row),
                    last_success_text=date(row.get("last_success")),
                    size_text=human_size(row.get("repository_bytes")),
                )
                rows.append(item)
            return encoded(
                {
                    "ok": True,
                    "destinations": rows,
                    "autostart": autostart_enabled(),
                    "open_requested": self.open_requested,
                }
            )
        except (Error, OSError, ValueError) as exc:
            return encoded({"ok": False, "error": str(exc)})

    @Slot(result=str)
    def RequestPopup(self):
        self.open_requested += 1
        return encoded({"ok": True})

    @Slot(bool, result=str)
    def Autostart(self, enabled):
        try:
            set_autostart(enabled)
            return encoded({"ok": True, "enabled": enabled})
        except OSError as exc:
            return encoded({"ok": False, "error": str(exc)})

    @Slot(str, str, str, result=str)
    def Action(self, command, name, options):
        try:
            extra = json.loads(options)
            if not isinstance(extra, dict):
                raise Error("Ungültige Optionen.")
            if command not in {
                "backup",
                "check",
                "cancel",
                "init",
                "stats",
                "snapshots",
                "ls",
                "restore",
                "log",
                "install",
                "pause",
            }:
                raise Error("Unbekannte Aktion.")
            args = [command]
            if command not in {"install", "pause"}:
                self.window.engine.dest(name)
                args += ["--dest", name, "--json"]
            if command == "backup" and extra.get("dry_run") is True:
                args += ["--dry-run"]
            if command in {"ls", "restore"}:
                for key in ("snapshot", "path"):
                    if not isinstance(extra.get(key), str) or not extra[key]:
                        raise Error("Snapshot und Pfad erforderlich.")
                    args += ["--" + key, extra[key]]
            if command == "restore" and "target" in extra:
                if not isinstance(extra["target"], str) or not extra["target"]:
                    raise Error("Ungültiges Wiederherstellungsziel.")
                args += ["--target", extra["target"]]
            # Bounded response cache. Never evict an operation that is still running.
            for key in list(self.results):
                if len(self.results) < 64:
                    break
                if self.results[key].get("done"):
                    del self.results[key]
            if len(self.results) >= 64:
                raise Error("Zu viele laufende Anfragen.")
            token = uuid.uuid4().hex
            self.results[token] = {"done": False}

            def ready(result):
                self.results[token] = {"done": True, "result": result}

            self.window.jobs.start(args, ready)
            return encoded({"ok": True, "request": token})
        except (Error, OSError, ValueError) as exc:
            return encoded({"ok": False, "error": str(exc)})

    @Slot(str, result=str)
    def Result(self, token):
        return encoded(
            self.results.get(
                token, {"done": True, "result": {"ok": False, "error": "Anfrage nicht mehr vorhanden."}}
            )
        )

    @Slot(str, str, result=str)
    def Dialog(self, action, name):
        actions = {
            "settings": self.window.settings,
            "key-set": self.window.set_key,
            "key-show": self.window.show_key,
            "keys": self.window.key_menu,
            "logs": self.window.logs,
        }
        if action not in actions:
            return encoded({"ok": False, "error": "Unbekannter Dialog."})
        try:
            if action != "settings":
                self.window.engine.dest(name)
                self.window.list.setCurrentRow(
                    next(i for i, r in enumerate(self.window.rows) if r["name"] == name)
                )
            # Reply before opening a modal dialog, keeping Plasma responsive.
            QTimer.singleShot(0, actions[action])
            return encoded({"ok": True})
        except (Error, StopIteration) as exc:
            return encoded({"ok": False, "error": str(exc)})

    @Slot(result=str)
    def Shutdown(self):
        if self.window.jobs.processes:
            return encoded({"ok": False, "error": "Es laufen noch Vorgänge."})
        QTimer.singleShot(0, QApplication.quit)
        return encoded({"ok": True})


def request_popup():
    app = QApplication.instance() or QApplication([sys.argv[0]])
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("Keine KDE-Sitzung erreichbar.", file=sys.stderr)
        return 1
    integrate_panel()
    request = QDBusMessage.createMethodCall(SERVICE, OBJECT, SERVICE, "RequestPopup")
    reply = bus.call(request)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        print(reply.errorMessage() + "\nBitte python install.py ausführen.", file=sys.stderr)
        return 1
    # Keep QApplication alive until synchronous D-Bus work has completed.
    app.processEvents()
    return 0


def main(config_dir=None, state_dir=None):
    app = QApplication([sys.argv[0]])
    app.setApplicationName("CachyOS Time Machine")
    app.setDesktopFileName("cachyos-time-machine")
    app.setQuitOnLastWindowClosed(False)
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("Keine D-Bus-Sitzung erreichbar.", file=sys.stderr)
        return 1
    if not bus.registerService(SERVICE):
        return 0  # An already running instance owns the service.
    window = Window(config_dir, state_dir, native_panel=True)
    bridge = Bridge(window)
    if not bus.registerObject(OBJECT, bridge, QDBusConnection.RegisterOption.ExportAllSlots):
        return 1
    return app.exec()
