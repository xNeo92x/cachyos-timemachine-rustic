"""CI only: real Samba -> KIO FUSE -> rustic, on an isolated session bus."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection

from timemachine.core import Engine, Error, atomic
from timemachine.network import kio_mounts, mounted_url


def main():
    base = Path(sys.argv[1])
    os.environ.update(
        XDG_CONFIG_HOME=str(base / "config-base"), XDG_STATE_HOME=str(base / "state-base"),
        XDG_CACHE_HOME=str(base / "cache"), XDG_RUNTIME_DIR=str(base / "runtime"),
    )
    Path(os.environ["XDG_RUNTIME_DIR"]).mkdir(mode=0o700)
    app = QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    binary = next(p for p in (
        "/usr/lib/kio-fuse", "/usr/lib/x86_64-linux-gnu/libexec/kio-fuse"
    ) if Path(p).is_file())
    mount = base / "mount one"
    mount.mkdir()

    def start(folder):
        child = subprocess.Popen([binary, "-f", str(folder)])
        deadline = time.monotonic() + 10
        while not bus.interface().isServiceRegistered("org.kde.KIOFuse").value():
            app.processEvents()
            assert child.poll() is None, "KIO FUSE exited"
            assert time.monotonic() < deadline, "KIO FUSE did not register"
            time.sleep(0.05)
        return child

    child = start(mount)
    try:
        source = base / "source"
        source.mkdir()
        (source / "üñïcode [file].txt").write_text("real SMB backup and restore")
        url = "smb://guest@127.0.0.1/Backups/Repository%20space"
        config = {
            "source": str(source), "rustic_binary": str(Path(sys.argv[2]).absolute()),
            "destinations": [{"name": "nas", "repository": url}],
        }
        atomic(base / "config/config.json", config)
        engine = Engine(base / "config", base / "state")
        engine.set_key("nas", "test-only-password")
        engine.initialize("nas")
        assert (base / "share/Repository space/config").is_file(), "Repository not written to SMB server"
        assert any(root == mount for _, root in kio_mounts())
        # A Qt native picker may return the mounted local path; persist its URL.
        local_repository = mount / "smb/guest@127.0.0.1/Backups/Repository space"
        assert mounted_url(local_repository) == url
        engine.backup("nas")
        snapshot = engine.snapshots("nas")[0]["id"]
        engine.check("nas")
        # Simulate another login with a different FUSE mountpoint.
        child.terminate()
        child.wait(timeout=10)
        deadline = time.monotonic() + 5
        while bus.interface().isServiceRegistered("org.kde.KIOFuse").value():
            assert time.monotonic() < deadline
            time.sleep(0.05)
        second_mount = base / "mount two"
        second_mount.mkdir()
        child = start(second_mount)
        engine = Engine(base / "config", base / "state")
        restored = engine.restore("nas", snapshot, str(source / "üñïcode [file].txt"), str(base / "restored"))
        assert Path(restored["restored"]).read_text() == "real SMB backup and restore"
        assert engine.dest("nas")["repository"] == url
        # Disconnect transport, and prove a plain local directory cannot be used instead.
        child.terminate()
        child.wait(timeout=10)
        subprocess.run([shutil.which("fusermount3"), "-uz", str(second_mount)], check=False)
        subprocess.run([
            "sudo", "smbcontrol", "--configfile=" + str(base / "smb.conf"), "smbd", "shutdown"
        ], check=True)
        deadline = time.monotonic() + 10
        import socket

        while True:
            try:
                with socket.create_connection(("127.0.0.1", 445), timeout=1):
                    pass
            except OSError:
                break
            assert time.monotonic() < deadline, "SMB server did not stop"
            time.sleep(0.05)
        try:
            engine.snapshots("nas")
        except Error:
            pass
        else:
            raise AssertionError("Disconnected NAS unexpectedly succeeded")
        assert not list(second_mount.iterdir()), "Disconnected NAS created local backup files"
        print("NAS_SMB_BACKUP_RESTORE_RECONNECT_OK")
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)


if __name__ == "__main__":
    main()
