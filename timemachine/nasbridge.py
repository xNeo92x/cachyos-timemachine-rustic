"""Private rustic REST adapter with buffered I/O to a pinned NAS directory.

KIO's FileJob path opens/seeks/writes/closes for each FUSE write. Buffering
encrypted pack uploads avoids forwarding rustic's small local-backend writes.
Only the loopback interface is used, with an unguessable per-process URL token.
Repository files retain the normal rustic filesystem layout and format.
"""

import contextlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BUFFER_SIZE = 1024 * 1024
TYPES = {"data", "index", "snapshots", "keys", "locks"}
ID = re.compile(r"[a-f0-9]{64}")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


def directory(parent, name, create=False):
    if create:
        with contextlib.suppress(FileExistsError):
            os.mkdir(name, mode=0o700, dir_fd=parent)
    return os.open(name, DIR_FLAGS, dir_fd=parent)


class NasBridge:
    def __init__(self, repository):
        # Do not resolve/canonicalize /proc/self/fd: that would lose the pin and
        # allow writes to a plain local directory after a lazy NAS unmount.
        self.fd = os.open(repository, DIR_FLAGS & ~os.O_NOFOLLOW)
        self.token = secrets.token_urlsafe(32)
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.written = 0
        self.server = None
        self.thread = None

    def __enter__(self):
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self.server.daemon_threads = True
            self.server.bridge = self
            self.url = f"rest:http://127.0.0.1:{self.server.server_port}/{self.token}/"
            self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            self.thread.start()
            return self
        except BaseException:
            if self.server:
                self.server.server_close()
            os.close(self.fd)
            raise

    def __exit__(self, *_):
        with self.lock:
            self.stopped.set()
            os.close(self.fd)
            self.fd = None
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def acquire(self):
        with self.lock:
            if self.stopped.is_set():
                raise ConnectionError("bridge stopped")
            return os.dup(self.fd)

    def bytes_written(self):
        with self.lock:
            return self.written

    def count(self, amount):
        with self.lock:
            self.written += amount


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass  # Never log the URL token or repository filenames to stderr.

    def reply(self, code, body=b"", *, length=None, headers=None):
        self.replied = True
        self.send_response(code)
        self.send_header("Content-Length", str(len(body) if length is None else length))
        self.send_header("Connection", "close")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.dispatch()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def dispatch(self):
        bridge = self.server.bridge
        self.root = None
        self.replied = False
        try:
            self.connection.settimeout(30)
            url = urlsplit(self.path)
            pieces = url.path.split("/")
            if len(pieces) < 3 or not hmac.compare_digest(pieces[1], bridge.token):
                self.reply(403)
                return
            if bridge.stopped.is_set():
                self.reply(503)
                return
            self.root = bridge.acquire()
            parts = pieces[2:]
            if self.command == "POST" and parts == [""] and url.query == "create=true":
                fd = os.dup(self.root)
                try:
                    for name in TYPES:
                        child = directory(fd, name, create=True)
                        os.close(child)
                finally:
                    os.close(fd)
                self.reply(200)
                return
            if url.query or url.fragment:
                self.reply(400)
                return
            if self.command == "GET" and len(parts) == 2 and parts[0] in TYPES and parts[1] == "":
                self.list_files(parts[0])
                return
            if parts == ["config"]:
                kind, name = "config", "config"
            elif len(parts) == 2 and parts[0] in TYPES and ID.fullmatch(parts[1]):
                kind, name = parts
            else:
                self.reply(400)
                return
            self.file(kind, name)
        except FileNotFoundError:
            if not self.replied:
                self.reply(404)
        except (ConnectionError, TimeoutError):
            self.close_connection = True
        except (OSError, ValueError, OverflowError):
            # Errors are deliberately generic, without paths/credentials. The
            # native client receives failure and cannot record a successful backup.
            with contextlib.suppress(ConnectionError, OSError):
                if not self.replied:
                    self.reply(500)
        finally:
            self.close_connection = True
            if self.root is not None:
                os.close(self.root)

    def list_files(self, kind):
        fd = directory(self.root, kind)
        try:
            result = []

            def add_files(parent):
                for name in os.listdir(parent):
                    if ID.fullmatch(name):
                        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                        if stat.S_ISREG(info.st_mode):
                            result.append({"name": name, "size": info.st_size})

            add_files(fd)
            if kind == "data":
                for name in os.listdir(fd):
                    if re.fullmatch(r"[a-f0-9]{2}", name):
                        child = directory(fd, name)
                        try:
                            add_files(child)
                        finally:
                            os.close(child)
        finally:
            os.close(fd)
        self.reply(200, json.dumps(sorted(result, key=lambda item: item["name"])).encode(),
                   headers={"Content-Type": "application/vnd.x.restic.rest.v2"})

    def parent(self, kind, name, create):
        fd = os.dup(self.root)
        try:
            if kind != "config":
                child = directory(fd, kind, create)
                os.close(fd)
                fd = child
            if kind == "data":
                # Read existing flat REST layouts too; new files use rustic's
                # normal two-character pack directories.
                try:
                    os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    child = directory(fd, name[:2], create)
                    os.close(fd)
                    fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def file(self, kind, name):
        parent = self.parent(kind, name, self.command == "POST")
        try:
            if self.command == "DELETE":
                os.unlink(name, dir_fd=parent)
                self.reply(200)
            elif self.command == "POST":
                self.upload(parent, kind, name)
            else:
                fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    size = os.fstat(fd).st_size
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise ValueError("not a regular file")
                    start, end = 0, size - 1
                    headers = {"Content-Type": "application/octet-stream", "Accept-Ranges": "bytes"}
                    code = 200
                    requested = self.headers.get("Range")
                    if requested and self.command == "GET":
                        match = re.fullmatch(r"bytes=(\d+)-(\d*)", requested)
                        if not match:
                            self.reply(416)
                            return
                        start = int(match[1])
                        end = min(int(match[2]) if match[2] else size - 1, size - 1)
                        if start > end:
                            self.reply(416)
                            return
                        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
                        code = 206
                    length = max(0, end - start + 1)
                    self.reply(code, length=length, headers=headers)
                    if self.command == "GET":
                        os.lseek(fd, start, os.SEEK_SET)
                        while length:
                            block = os.read(fd, min(BUFFER_SIZE, length))
                            if not block:
                                raise OSError("short repository read")
                            self.wfile.write(block)
                            length -= len(block)
                finally:
                    os.close(fd)
        finally:
            os.close(parent)

    def body_blocks(self):
        """Decode reqwest's streaming uploads, coalescing small HTTP chunks."""
        length = self.headers.get("Content-Length")
        encoding = self.headers.get("Transfer-Encoding")
        chunked = encoding is not None and encoding.lower() == "chunked"
        if encoding and (not chunked or length is not None):
            raise ValueError("ambiguous request body")
        if not chunked and (length is None or not length.isdecimal()):
            raise ValueError("missing request length")
        remaining = 0 if chunked else int(length)
        buffer = bytearray()
        while True:
            if self.server.bridge.stopped.is_set():
                raise ConnectionError("operation stopped")
            if chunked and remaining == 0:
                header = self.rfile.readline(128)
                match = re.fullmatch(rb"([0-9a-fA-F]{1,16})(?:;[^\r\n]*)?\r\n", header)
                if not match:
                    raise ValueError("invalid HTTP chunk")
                remaining = int(match[1], 16)
                if remaining == 0:
                    size = 0
                    while True:
                        trailer = self.rfile.readline(8193)
                        size += len(trailer)
                        if size > 8192 or not trailer.endswith(b"\r\n"):
                            raise ValueError("invalid HTTP trailer")
                        if trailer == b"\r\n":
                            break
                    break
            if remaining == 0:
                break
            block = self.rfile.read(min(BUFFER_SIZE - len(buffer), remaining))
            if not block:
                raise ConnectionError("incomplete upload")
            buffer.extend(block)
            remaining -= len(block)
            if chunked and remaining == 0 and self.rfile.read(2) != b"\r\n":
                raise ValueError("invalid HTTP chunk ending")
            if len(buffer) == BUFFER_SIZE:
                yield buffer
                buffer = bytearray()
        if buffer:
            yield buffer

    def upload(self, parent, kind, name):
        temporary = ".ctm-" + secrets.token_hex(16) + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            for block in self.body_blocks():
                pending = memoryview(block)
                while pending:
                    written = os.write(fd, pending)
                    if written == 0:
                        raise OSError("short repository write")
                    if kind == "data":
                        self.server.bridge.count(written)
                    pending = pending[written:]
            os.fsync(fd)
            if self.server.bridge.stopped.is_set():
                raise ConnectionError("operation stopped")
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            self.reply(200)
        finally:
            os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent)
