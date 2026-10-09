"""Exercise repository mapping with real rustic and reject disconnected mounts."""

import os
from pathlib import Path

import pytest

from timemachine import network
from timemachine.core import Engine, Error, atomic, validate


@pytest.mark.parametrize("url", [
    "smb://server", "smb://server/", "smb:///share", "smb://server/share/../other",
    "smb://server/share?password=x", "smb://server/share/%00", "smb://neo:secret@server/share",
])
def test_reject_invalid_or_password_bearing_nas_urls(url):
    with pytest.raises(Error):
        validate({"destinations": [{"name": "nas", "repository": url}]})


def test_same_share_lock_ignores_user_encoding_and_trailing_slash(configured):
    engine, _, _ = configured
    engine.config["destinations"] = [
        {"name": "neo", "repository": "smb://neo@NAS.local:445/NAS/Backup Folder/"},
        {"name": "other", "repository": "smb://someone@nas.local/NAS/Backup%20Folder"},
    ]
    atomic(engine.config_path, engine.config)
    second = Engine(engine.config_dir, engine.state_dir)
    with engine.operation("neo", "backup"):
        with pytest.raises(Error, match="bereits"):
            with second.operation("other", "backup"):
                pass


def test_existing_local_directory_is_not_a_connected_nas(configured, monkeypatch):
    engine, _, repo = configured
    repo.mkdir()
    engine.config["destinations"][0]["repository"] = "smb://neo@nas.local/NAS/Backup"
    monkeypatch.setattr(network, "kio_call", lambda *args: str(repo))
    monkeypatch.setattr(network, "kio_mounts", lambda: [])
    previous = "2025-01-01T00:00:00+00:00"
    engine.update("test", last_success=previous)
    with pytest.raises(Error, match="nicht als KDE-Netzwerkdateisystem"):
        engine.backup("test")
    assert not list(repo.iterdir())
    assert engine.state("test")["last_success"] == previous
    assert engine.state("test")["last_backup_status"] == "failed"


@pytest.mark.integration
def test_nas_url_reconnects_each_process_and_pins_rustic_directory(rustic_engine, monkeypatch, tmp_path):
    engine, source, repo = rustic_engine
    url = "smb://neo@nas.local/NAS/Backup%20Folder"
    engine.config["destinations"][0]["repository"] = url
    atomic(engine.config_path, engine.config)
    calls = []

    def mount(member, value):
        assert member == "mountUrl" and value == url
        calls.append(value)
        return str(repo)

    # Emulate only KDE's mount transport; all backup/restore I/O uses real rustic.
    fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
    try:
        info = Path(f"/proc/self/fdinfo/{fd}").read_text()
    finally:
        os.close(fd)
    mount_id = next(line.split()[1] for line in info.splitlines() if line.startswith("mnt_id:"))
    monkeypatch.setattr(network, "kio_call", mount)
    monkeypatch.setattr(network, "kio_mounts", lambda: [(mount_id, repo)])
    (source / "NAS marker.txt").write_text("from NAS repository")
    engine.backup("test")
    # A fresh process/engine after login must resolve the URL again.
    engine = Engine(engine.config_dir, engine.state_dir)
    snapshot = engine.snapshots("test")[0]["id"]
    engine.check("test")
    restored = engine.restore("test", snapshot, str(source / "NAS marker.txt"), str(tmp_path / "restored"))
    assert Path(restored["restored"]).read_text() == "from NAS repository"
    assert len(calls) >= 5
    assert engine.dest("test")["repository"] == url
    assert "/proc/self/fd/" not in engine.config_path.read_text()


def test_disconnected_nas_does_not_create_local_fallback(configured, monkeypatch):
    engine, _, repo = configured
    engine.config["destinations"][0]["repository"] = "smb://neo@nas.local/NAS/Backup"

    def offline(*args):
        raise network.NetworkError("NAS nicht erreichbar")

    monkeypatch.setattr(network, "kio_call", offline)
    with pytest.raises(Error, match="NAS nicht erreichbar"):
        engine.initialize("test")
    assert not repo.exists()
