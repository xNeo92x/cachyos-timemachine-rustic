"""REST compatibility, upload atomicity and mount pinning for buffered SMB."""

import contextlib
import http.client
import os
import threading
from urllib.parse import urlsplit

import pytest

from timemachine import core, nasbridge
from timemachine.core import Error, atomic
from timemachine.nasbridge import BUFFER_SIZE, NasBridge


def request(bridge, method, path, body=None, **kwargs):
    url = urlsplit(bridge.url.removeprefix("rest:"))
    client = http.client.HTTPConnection(url.hostname, url.port, timeout=10)
    try:
        client.request(method, url.path + path, body=body, **kwargs)
        response = client.getresponse()
        return response.status, response.read(), dict(response.headers)
    finally:
        client.close()


@pytest.fixture
def bridge(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with NasBridge(repo) as bridge:
        assert request(bridge, "POST", "?create=true")[0] == 200
        yield bridge, repo


def test_chunked_uploads_coalesce_and_remain_filesystem_compatible(bridge, monkeypatch):
    server, repo = bridge
    calls = []
    write = nasbridge.os.write

    def recorded(fd, block):
        calls.append(len(block))
        return write(fd, block)

    monkeypatch.setattr(nasbridge.os, "write", recorded)
    data = os.urandom(2 * BUFFER_SIZE + 23)
    name = "a" * 64
    chunks = (data[pos:pos + 8192] for pos in range(0, len(data), 8192))
    assert request(server, "POST", "data/" + name, body=chunks, encode_chunked=True)[0] == 200
    assert calls == [BUFFER_SIZE, BUFFER_SIZE, 23]
    assert server.bytes_written() == len(data)
    assert (repo / "data/aa" / name).read_bytes() == data
    assert request(server, "HEAD", "data/" + name)[2]["Content-Length"] == str(len(data))
    status, body, headers = request(server, "GET", "data/" + name, headers={"Range": "bytes=10-99"})
    assert status == 206 and body == data[10:100] and headers["Content-Range"] == f"bytes 10-99/{len(data)}"
    assert request(server, "GET", "data/" + name, headers={"Range": "bytes=999999999-"})[0] == 416
    assert name.encode() in request(server, "GET", "data/")[1]
    assert request(server, "DELETE", "data/" + name)[0] == 200
    assert request(server, "GET", "data/" + name)[0] == 404


def test_paths_tokens_and_symlinks_cannot_escape_repository(bridge, tmp_path):
    server, repo = bridge
    assert request(server, "POST", "../config", b"bad")[0] == 400
    assert request(server, "POST", "data/%2e%2e", b"bad")[0] == 400
    token = server.token
    server.token = "different-token"
    try:
        server.url = server.url.replace(token, "wrong-token")
        assert request(server, "GET", "config")[0] == 403
    finally:
        server.token = token
        server.url = server.url.replace("wrong-token", token)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "data/aa").symlink_to(outside, target_is_directory=True)
    assert request(server, "POST", "data/" + "a" * 64, b"bad")[0] == 500
    assert not list(outside.iterdir())
    (outside / "secret").write_bytes(b"secret")
    (repo / "config").symlink_to(outside / "secret")
    assert request(server, "GET", "config")[0] == 500
    assert (outside / "secret").read_bytes() == b"secret"


def test_partial_malformed_upload_and_fsync_failure_never_publish(bridge, monkeypatch):
    server, repo = bridge
    assert request(server, "POST", "config", b"old")[0] == 200
    # Raw malformed chunk after one full block forces cleanup of a written temp.
    body = f"{BUFFER_SIZE:x}\r\n".encode() + b"x" * BUFFER_SIZE + b"\r\nINVALID\r\n"
    assert request(server, "POST", "config", body, headers={"Transfer-Encoding": "chunked"})[0] == 500
    assert (repo / "config").read_bytes() == b"old"
    assert not list(repo.glob(".ctm-*.tmp"))

    def fail(_):
        raise OSError("simulated lost transport")

    monkeypatch.setattr(nasbridge.os, "fsync", fail)
    assert request(server, "POST", "config", b"new")[0] == 500
    assert (repo / "config").read_bytes() == b"old"
    assert not list(repo.glob(".ctm-*.tmp"))


def test_directory_descriptor_remains_pinned_after_path_replacement(bridge):
    server, repo = bridge
    old = repo.with_name("original")
    repo.rename(old)
    repo.mkdir()
    assert request(server, "POST", "config", b"pinned")[0] == 200
    assert (old / "config").read_bytes() == b"pinned"
    assert not list(repo.iterdir())


def test_shutdown_rejects_active_upload_before_atomic_publish(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    server = NasBridge(repo).__enter__()
    reached, release = threading.Event(), threading.Event()
    fsync = nasbridge.os.fsync

    def pause(fd):
        reached.set()
        assert release.wait(10)
        fsync(fd)

    monkeypatch.setattr(nasbridge.os, "fsync", pause)
    failures = []

    def upload():
        try:
            request(server, "POST", "config", b"unfinished")
        except (ConnectionError, http.client.HTTPException) as exc:
            failures.append(exc)

    worker = threading.Thread(target=upload)
    worker.start()
    try:
        assert reached.wait(5)
        server.__exit__()
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive() and failures
    assert not (repo / "config").exists() and not list(repo.glob(".ctm-*.tmp"))


@pytest.mark.integration
def test_real_rustic_existing_repo_roundtrip_buffered_and_local(rustic_engine, monkeypatch):
    engine, source, repo = rustic_engine
    # Repository was initialized by rustic's original filesystem backend.
    data = os.urandom(16 * 1024 ** 2)
    large = source / "unique üñïcode.bin"
    large.write_bytes(data)
    url = "smb://nas/share/repo"
    engine.config["destinations"][0]["repository"] = url
    atomic(engine.config_path, engine.config)

    @contextlib.contextmanager
    def pinned(_):
        fd = os.open(repo, os.O_DIRECTORY | os.O_RDONLY)
        try:
            yield f"/proc/self/fd/{fd}", (fd,)
        finally:
            os.close(fd)

    monkeypatch.setattr(core, "repository_access", pinned)
    observed = []
    update = engine.update

    def observe(name, **changes):
        if "progress" in changes:
            observed.append(changes["progress"].copy())
        return update(name, **changes)

    monkeypatch.setattr(engine, "update", observe)
    engine.backup("test")
    assert any(item.get("repository_bytes_written", 0) >= len(data) for item in observed)
    first = engine.snapshots("test")[0]["id"]
    engine.run("test", ["check", "--read-data"], timeout=None)
    result = engine.restore("test", first, str(large), str(repo.parent / "restored-buffered"))
    assert open(result["restored"], "rb").read() == data
    engine.config["destinations"][0]["nas_backend"] = "local"
    atomic(engine.config_path, engine.config)
    engine.run("test", ["check", "--read-data"], timeout=None)
    result = engine.restore("test", first, str(large), str(repo.parent / "restored-local"))
    assert open(result["restored"], "rb").read() == data
    engine.backup("test")
    assert len(engine.snapshots("test")) == 2
    # Reopen through REST after a legacy backup, including repeated listing/deletion.
    engine.config["destinations"][0]["nas_backend"] = "buffered"
    atomic(engine.config_path, engine.config)
    engine.run("test", ["forget", first], timeout=None)
    engine.run("test", ["prune"], timeout=None)
    engine.run("test", ["check", "--read-data"], timeout=None)
    assert len(engine.snapshots("test")) == 1
    assert engine.state("test")["last_success"]
    assert "rest:http" not in engine.dest("test")["repository"]


def test_invalid_nas_backend_is_rejected(configured):
    engine, _, _ = configured
    engine.config["destinations"][0]["nas_backend"] = "invalid"
    with pytest.raises(Error, match="nas_backend"):
        core.validate(engine.config)
