"""Exercise native KDE Open/Save/Cancel buttons, including a real SMB directory."""

import base64
import getpass
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from timemachine.core import Engine, atomic
from timemachine.gui import Window


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    def wait(condition):
        deadline = time.monotonic() + 20
        while not condition():
            app.processEvents()
            if time.monotonic() > deadline:
                raise AssertionError("KDE dialog timed out")
            time.sleep(0.02)
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix="kde-picker-") as directory:
        base = Path(directory)
        base.chmod(0o755)
        share = base / "share"
        nas_folder = share / "CachyOS Backup"
        nas_folder.mkdir(parents=True)
        samba = base / "samba"
        samba.mkdir()
        smb_config = base / "smb.conf"
        smb_config.write_text(f"""[global]
server role = standalone server
smb ports = 1445
interfaces = 127.0.0.1
bind interfaces only = yes
map to guest = Bad User
guest account = {getpass.getuser()}
log file = {samba}/log.%m
pid directory = {samba}
lock directory = {samba}
state directory = {samba}
cache directory = {samba}
private dir = {samba}
ncalrpc dir = {samba}/ncalrpc
[NAS]
path = {share}
guest ok = yes
read only = no
force user = {getpass.getuser()}
""")
        with (base / "smbd.log").open("w") as log:
            server = subprocess.Popen(
                [shutil.which("smbd"), "--foreground", "--no-process-group", "--debug-stdout", "--debuglevel=3", "--configfile=" + str(smb_config)],
                stdin=subprocess.PIPE, stdout=log, stderr=log, start_new_session=True,
            )
            window = None
            try:
                def listening():
                    assert server.poll() is None, "\n".join(
                        path.read_text(errors="replace") for path in [base / "smbd.log", *samba.glob("log.*")]
                    )
                    try:
                        with socket.create_connection(("127.0.0.1", 1445), timeout=0.2):
                            return True
                    except OSError:
                        return False

                wait(listening)
                config = base / "config"
                Engine.create_config(config)
                atomic(config / "config.json", {
                    "source": str(base), "destinations": [{"name": "nas", "repository": str(base / "old")}],
                })
                window = Window(config, base / "state", native_panel=True)
                window.jobs.start = lambda *args: None
                errors = []
                window.error = errors.append

                wayland = QApplication.platformName() == "wayland"
                assert QApplication.platformName() in ("xcb", "wayland")

                def chooser_visible(pid):
                    if wayland:
                        tree = json.loads(subprocess.check_output(["swaymsg", "-t", "get_tree"], text=True))
                        def find(node):
                            return node.get("pid") == pid or any(find(child) for child in node.get("nodes", []) + node.get("floating_nodes", []))
                        return find(tree)
                    result = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)], capture_output=True, text=True)
                    return result.stdout.splitlines()

                def keys(*sequence):
                    if wayland:
                        subprocess.run(["wtype", *sequence], check=True)
                    else:
                        raise AssertionError("Use X11 helper")

                def choose(settings, value, directory=True):
                    picker = settings.file_picker
                    wait(lambda: chooser_visible(picker.process.processId()))
                    # The Name field is independent of the navigation bar. Typing
                    # only into Ctrl+L retains the previous selected filename.
                    entered = value if directory else '"' + value + '"'
                    if wayland:
                        keys("-M", "alt", "-k", "n", "-m", "alt")
                        keys("-M", "ctrl", "-k", "a", "-m", "ctrl", "--", entered)
                        keys("-M", "alt", "-k", "o", "-m", "alt")
                    else:
                        wid = chooser_visible(picker.process.processId())[-1]
                        subprocess.run(["xdotool", "windowactivate", "--sync", wid,
                                        "key", "--clearmodifiers", "alt+n", "ctrl+a"], check=True)
                        subprocess.run(["xdotool", "type", "--clearmodifiers", "--", entered], check=True)
                        subprocess.run(["xdotool", "key", "--clearmodifiers", "alt+o"], check=True)
                    try:
                        wait(lambda: settings.file_picker is None)
                    except AssertionError:
                        print("PICKER_TIMEOUT value=" + value, flush=True)
                        print(bytes(picker.process.readAllStandardError()).decode(errors="replace"), flush=True)
                        image = base / "picker.png"
                        if wayland:
                            subprocess.run(["grim", str(image)], check=True)
                            print(subprocess.check_output(["swaymsg", "-t", "get_tree"], text=True), flush=True)
                        else:
                            app.primaryScreen().grabWindow(0).save(str(image))
                        print("PICKER_SCREENSHOT=" + base64.b64encode(image.read_bytes()).decode(), flush=True)
                        picker.cancel()
                        wait(lambda: settings.file_picker is None)
                        raise
                    assert not errors, errors
                    assert settings.isVisible() and settings.isEnabled(), "Open closed Settings"

                for value in [str(nas_folder), "smb://guest@127.0.0.1:1445/NAS/CachyOS%20Backup"]:
                    window.settings()
                    settings = window.settings_dialog
                    wait(settings.isVisible)
                    settings.pick_repository(network=value.startswith("smb://"))
                    choose(settings, value)
                    assert window.settings_dialog is settings
                    assert settings.fields["repository"].text() == value
                    assert window.engine.dest("nas")["repository"] != value, "Open saved prematurely"
                    box = next(b for b in settings.findChildren(QDialogButtonBox) if b.parent() is settings)
                    QTest.mouseClick(box.button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
                    wait(lambda: window.settings_dialog is None)
                    assert window.engine.dest("nas")["repository"] == value
                    window.settings()
                    assert window.settings_dialog.fields["repository"].text() == value
                    window.settings_dialog.reject()
                    app.processEvents()
                window.settings()
                settings = window.settings_dialog
                settings.pick_paths(settings.sources, directory=True)
                choose(settings, str(nas_folder))
                assert str(nas_folder) in settings.sources.toPlainText().splitlines()
                file = nas_folder / "source file.txt"
                file.write_text("source")
                settings.pick_paths(settings.sources)
                choose(settings, str(file), directory=False)
                assert str(file) in settings.sources.toPlainText().splitlines()
                settings.pick_paths(settings.excludes, directory=True, excluded=True)
                choose(settings, str(nas_folder))
                assert "!" + str(nas_folder) + "/**" in settings.excludes.toPlainText().splitlines()
                settings.save()
                window.settings()
                assert str(file) in window.settings_dialog.sources.toPlainText().splitlines()
                window.settings_dialog.reject()
                print("KDE_NATIVE_LOCAL_AND_SMB_PICKER_OPEN_SAVE_REOPEN_OK platform=" + QApplication.platformName(), flush=True)
            finally:
                if window is not None:
                    window.timer.stop()
                    window.close()
                    window.deleteLater()
                    app.processEvents()
                if server.poll() is None:
                    os.killpg(server.pid, signal.SIGTERM)
                    server.wait(timeout=10)
                server.stdin.close()


if __name__ == "__main__":
    main()
