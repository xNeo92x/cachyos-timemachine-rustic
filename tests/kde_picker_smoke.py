"""Exercise native KDE Open/Save/Cancel buttons, including a real SMB directory."""

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

from PySide6.QtCore import Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

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
interfaces = 127.0.0.1
bind interfaces only = yes
map to guest = Bad User
log file = {samba}/log.%m
pid directory = {samba}
lock directory = {samba}
state directory = {samba}
cache directory = {samba}
private dir = {samba}
[NAS]
path = {share}
guest ok = yes
read only = no
force user = root
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
                        with socket.create_connection(("127.0.0.1", 445), timeout=0.2):
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

                for url in [QUrl.fromLocalFile(str(nas_folder)), QUrl("smb://guest@127.0.0.1/NAS/CachyOS%20Backup")]:
                    window.settings()
                    settings = window.settings_dialog
                    wait(settings.isVisible)
                    settings.pick_repository(network=not url.isLocalFile())
                    picker = settings.repository_dialog

                    def native_dialog():
                        return next((w for w in app.topLevelWidgets()
                                     if w.isVisible() and w.metaObject().className() == "KDEPlatformFileDialog"), None)

                    wait(native_dialog)
                    native = native_dialog()
                    picker.selectUrl(url)
                    open_button = next(b for b in native.findChildren(QPushButton)
                                       if b.text().replace("&", "") in ("Open", "Öffnen"))
                    wait(open_button.isEnabled)
                    QTest.qWait(500)
                    QTest.mouseClick(open_button, Qt.MouseButton.LeftButton)
                    wait(lambda: settings.repository_dialog is None)
                    assert not errors, errors
                    assert window.settings_dialog is settings and settings.isVisible(), "Open closed Settings"
                    expected = url.toLocalFile() if url.isLocalFile() else url.toString(QUrl.FullyEncoded)
                    assert settings.fields["repository"].text() == expected
                    assert window.engine.dest("nas")["repository"] != expected, "Open saved prematurely"
                    # Only the settings Save button commits and closes the parent dialog.
                    box = next(b for b in settings.findChildren(QDialogButtonBox) if b.parent() is settings)
                    QTest.mouseClick(box.button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
                    wait(lambda: window.settings_dialog is None)
                    assert window.engine.dest("nas")["repository"] == expected
                    window.settings()
                    assert window.settings_dialog.fields["repository"].text() == expected
                    window.settings_dialog.reject()
                    app.processEvents()
                print("KDE_NATIVE_LOCAL_AND_SMB_PICKER_OPEN_SAVE_REOPEN_OK", flush=True)
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
