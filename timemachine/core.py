"""Headless backup engine. Only this module invokes rustic or writes state."""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

from .i18n import CHOICES, configure, tr
from .network import NetworkError, is_smb, kio_mounts, repository_access, smb_url

APP = "cachyos-time-machine"
RETENTION = {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 3}
MAX_OUTPUT = 32 * 1024 * 1024


class Error(RuntimeError):
    """A user-facing operation error."""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def expand(value):
    return Path(os.path.expandvars(os.path.expanduser(value))).absolute()


def atomic(path, value):
    """Replace files atomically; private state and secrets always use mode 0600."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        raise Error(tr("Ungültige Datei {p0}: {p1}", p0=path, p1=exc)) from exc


def validate(config):
    if not isinstance(config, dict):
        raise Error(tr("Konfiguration muss ein JSON-Objekt sein."))
    if config.get("language", "system") not in CHOICES:
        raise Error(tr("language muss system, de oder en sein."))
    sources = config.get("source", "~")
    sources = [sources] if isinstance(sources, str) else sources
    if not isinstance(sources, list) or not sources or any(not isinstance(x, str) or not x for x in sources):
        raise Error(tr("source muss ein Pfad oder eine nicht leere Pfadliste sein."))
    destinations = config.get("destinations")
    if not isinstance(destinations, list) or not destinations:
        raise Error(tr("Mindestens ein Backup-Ziel ist erforderlich."))
    names = set()
    for dest in destinations:
        if not isinstance(dest, dict):
            raise Error(tr("Jedes Ziel muss ein Objekt sein."))
        name = dest.get("name", "")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name)
            or name in names
        ):
            raise Error(tr("Zielnamen müssen eindeutig sein und nur Buchstaben, Ziffern, _ oder - enthalten."))
        names.add(name)
        if not isinstance(dest.get("repository"), str) or not dest["repository"]:
            raise Error(tr("Repository fehlt für {p0}.", p0=name))
        if is_smb(dest["repository"]):
            try:
                dest["repository"] = smb_url(dest["repository"])
            except NetworkError as exc:
                raise Error(str(exc)) from exc
        if dest["repository"].startswith(("sftp:", "s3:", "b2:", "azure:", "gs:")):
            raise Error(
                tr("restic-URLs werden nicht übernommen. Nutze opendal:sftp / opendal:s3 mit options oder rclone:remote:path.")
            )
        for key in (
            "schedule",
            "display_name",
            "pre_command",
            "on_failure_command",
            "env_file",
            "password_file",
        ):
            if key in dest and (not isinstance(dest[key], str) or any(c in dest[key] for c in "\n\r\0")):
                raise Error(tr("Ungültiger Wert für {p0}.{p1}.", p0=name, p1=key))
        for key in ("options", "env"):
            if key in dest and (
                not isinstance(dest[key], dict)
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in dest[key].items())
            ):
                raise Error(tr("{p0} muss ein Objekt mit Zeichenketten sein.", p0=key))
        if "exclude_file" in config and not isinstance(config["exclude_file"], str):
            raise Error(tr("exclude_file muss eine Zeichenkette sein."))
        if "password_command" in dest and (
            not isinstance(dest["password_command"], str) or not dest["password_command"]
        ):
            raise Error(tr("password_command muss ein nicht leerer Befehl sein."))
        if "password_command" in dest and "password_file" in dest:
            raise Error(tr("Nutze password_file oder password_command, nicht beide."))
        retention = dest.get("retention", config.get("retention", RETENTION))
        if (
            not isinstance(retention, dict)
            or any(k not in RETENTION or type(v) is not int or v < 0 for k, v in retention.items())
            or not any(retention.values())
        ):
            raise Error(tr("Aufbewahrung benötigt mindestens eine positive Anzahl daily/weekly/monthly/yearly."))
        for key in ("stale_hours", "hook_timeout"):
            v = dest.get(key, config.get(key, 48 if key == "stale_hours" else 120))
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 < v <= 87600:
                raise Error(tr("Ungültiger Wert für {p0}.", p0=key))
    return config


def safe_snapshot(value):
    if not re.fullmatch(r"[0-9a-f]{8,64}", value):
        raise Error(tr("Ungültige Snapshot-ID."))
    return value


def safe_path(value):
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or "\0" in value
        or ".." in PurePosixPath(value).parts
    ):
        raise Error(tr("Snapshot-Pfad muss absolut sein und darf kein .. enthalten."))
    return str(PurePosixPath(value))


def proc_start(pid):
    """Read process identity, including containers with a host-mounted /proc."""
    try:
        if pid == os.getpid():
            return Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
        namespace = os.readlink("/proc/self/ns/pid")
        candidates = [Path(f"/proc/{pid}")]
        candidates.extend(p for p in Path("/proc").iterdir() if p.name.isdigit() and p.name != str(pid))
        for directory in candidates:
            try:
                if os.readlink(directory / "ns/pid") != namespace:
                    continue
                status = (directory / "status").read_text()
                ids = next(line.split()[1:] for line in status.splitlines() if line.startswith("NSpid:"))
                if int(ids[-1]) == pid:
                    return (directory / "stat").read_text().rsplit(")", 1)[1].split()[19]
            except (OSError, IndexError, StopIteration, ValueError):
                continue
    except (OSError, IndexError, ValueError):
        return None
    return None


def alive(state):
    pid = state.get("pid")
    return (
        type(pid) is int
        and pid > 1
        and state.get("proc_start") is not None
        and proc_start(pid) == state["proc_start"]
    )


class Engine:
    def __init__(self, config_dir=None, state_dir=None):
        self.config_dir = Path(
            config_dir or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
        )
        self.state_dir = Path(
            state_dir or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP
        )
        self.config_path = self.config_dir / "config.json"
        config = read_json(self.config_path, {})
        configure(config.get("language", "system") if isinstance(config, dict) else "system")
        self.config = validate(config)
        self.cancelled = False
        self.child = None
        self.current = None
        self.last_progress = 0.0
        self.prepared = set()

    @staticmethod
    def create_config(config_dir=None):
        base = Path(config_dir or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP)
        path = base / "config.json"
        if not path.exists():
            atomic(
                path,
                {
                    "source": "~",
                    "retention": RETENTION,
                    "destinations": [
                        {
                            "name": "backup-drive",
                            "display_name": tr("Backup-Laufwerk"),
                            "repository": "/run/media/CHANGE-ME/backup/rustic",
                            "schedule": "*-*-* 03:00:00",
                        }
                    ],
                },
            )
        exclude = base / "excludes.txt"
        if not exclude.exists():
            atomic(
                exclude,
                "# rustic-Globs: ! schließt aus, positive Muster schließen ein.\n!.cache/\n!.local/share/Trash/\n",
            )
        return path

    def dest(self, name):
        for dest in self.config["destinations"]:
            if dest["name"] == name:
                return dest
        raise Error(tr("Unbekanntes Backup-Ziel: {p0}", p0=name))

    def folder(self, name):
        self.dest(name)
        p = self.state_dir / name
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        return p

    def password_path(self, dest):
        return (
            expand(dest["password_file"])
            if "password_file" in dest
            else self.config_dir / "keys" / (dest["name"] + ".password")
        )

    def password_mode(self, dest):
        if "password_command" in dest:
            return "external"
        if self.password_path(dest).is_file():
            return "stored"
        return "missing" if "password_file" in dest else "none"

    def repository_identity(self, dest):
        ident = dest["repository"]
        if is_smb(ident):
            ident = smb_url(ident, identity=True)
        elif ":" not in ident:
            ident = str(expand(ident).resolve())
        return hashlib.sha256(ident.encode()).hexdigest()

    def remember_initialized(self, name):
        dest = self.dest(name)
        self.update(name, initialized_repository=self.repository_identity(dest),
                    initialized_without_password=self.password_mode(dest) == "none")

    def set_key(self, name, password):
        dest = self.dest(name)
        if "password_command" in dest:
            raise Error(tr("Dieses Ziel nutzt password_command. Verwalte den Schlüssel dort."))
        if not password or any(c in password for c in "\n\r\0"):
            raise Error(tr("Passwort darf nicht leer sein und keine Zeilenumbrüche enthalten."))
        path = self.password_path(dest)
        if path.exists():
            raise Error(tr("Schlüssel existiert bereits. Ein Austausch ändert das Repository-Passwort nicht."))
        with self.operation(name, "key-set"):
            if path.exists():
                raise Error(tr("Schlüssel existiert bereits. Ein Austausch ändert das Repository-Passwort nicht."))
            state = self.state(name)
            if (state.get("initialized_without_password")
                    and state.get("initialized_repository") == self.repository_identity(dest)):
                # Change the password of the EMPTY key, rather than leaving an
                # unprotected key alongside a new password-protected one.
                pending = path.with_name(path.name + ".pending")
                atomic(pending, password + "\n")
                try:
                    self.run(name, ["key", "password", "--new-password-file", str(pending)],
                             capture=False, timeout=None)
                except (Error, OSError) as exc:
                    # Retain the credential if transport failed after remote mutation.
                    raise Error(tr("Passwortänderung nicht bestätigt. Neues Passwort zur Wiederherstellung in {p0}. {p1}", p0=pending, p1=exc)) from exc
                os.replace(pending, path)
                self.remember_initialized(name)
            else:
                atomic(path, password + "\n")

    def show_key(self, name):
        dest = self.dest(name)
        if "password_command" in dest:
            raise Error(tr("Schlüssel wird extern über password_command verwaltet."))
        try:
            return self.password_path(dest).read_text().rstrip("\n")
        except OSError as exc:
            raise Error(tr("Noch kein Schlüssel gespeichert.")) from exc

    def save_1password(self, name, vault=None):
        title = f"Time Machine backup key ({name})"
        vault_args = ["--vault", vault] if vault else []
        # Use stdin for secrets; never put a password on the command line.
        listed = subprocess.run(
            ["op", "item", "list", "--format=json", *vault_args],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        if any(x.get("title") == title for x in json.loads(listed.stdout)):
            raise Error(tr("In 1Password existiert bereits ein Eintrag mit diesem Titel."))
        template = subprocess.run(
            ["op", "item", "template", "get", "Password"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        item = json.loads(template.stdout)
        item["title"] = title
        for field in item["fields"]:
            if field.get("id") == "password":
                field["value"] = self.show_key(name)
            if field.get("id") == "notesPlain":
                field["value"] = f"CachyOS Time Machine: {name}"
        subprocess.run(
            ["op", "item", "create", "--format=json", *vault_args, "-"],
            input=json.dumps(item),
            text=True,
            stdout=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )

    def state(self, name):
        state = read_json(self.folder(name) / "state.json", {})
        if state.get("status") == "running" and not alive(state):
            return {
                **state,
                "status": "interrupted",
                "phase": "interrupted",
                "error": tr("Vorgang wurde unterbrochen (z. B. Neustart)."),
            }
        return state

    def status(self):
        rows = []
        timers = read_json(self.state_dir / "timers.json", {})
        for dest in self.config["destinations"]:
            state = self.state(dest["name"])
            stale = False
            if state.get("last_success"):
                age = (
                    dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(state["last_success"])
                ).total_seconds()
                stale = age > 3600 * dest.get("stale_hours", self.config.get("stale_hours", 48))
            rows.append(
                {
                    "name": dest["name"],
                    "display_name": dest.get("display_name", dest["name"]),
                    "repository": re.sub(r"(://)[^/@]+@", r"\1***@", dest["repository"]),
                    "schedule": dest.get("schedule", ""),
                    "schedule_enabled": bool(
                        timers.get("enabled")
                        and APP + "-" + dest["name"] + ".timer" in timers.get("units", [])
                    ),
                    "has_key": "password_command" in dest or self.password_path(dest).is_file(),
                    "can_backup": self.password_mode(dest) != "missing",
                    "password_mode": self.password_mode(dest),
                    "stale": stale,
                    **state,
                }
            )
        return rows

    def update(self, name, **fields):
        path = self.folder(name) / "state.json"
        state = read_json(path, {})
        state.update(fields)
        atomic(path, state)

    def cancel(self, name):
        state = self.state(name)
        if state.get("status") != "running" or not alive(state):
            raise Error(tr("Kein laufender Vorgang für dieses Ziel."))
        os.kill(state["pid"], signal.SIGTERM)

    @contextlib.contextmanager
    def operation(self, name, phase):
        dest = self.dest(name)
        # Serialize writes across destinations pointing at the same repository.
        # Credentials/options may vary for the same URL; serializing too broadly
        # is preferable to letting two local writers modify the same repository.
        lock = self.state_dir / ("repo-" + self.repository_identity(dest) + ".lock")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.ExitStack() as stack:
            for path in (self.folder(name) / "operation.lock", lock):
                handle = stack.enter_context(path.open("a"))
                os.chmod(path, 0o600)
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise Error(tr("Für dieses Ziel/Repository läuft bereits ein Vorgang.")) from exc
            self.current = name
            self.cancelled = False
            self.update(
                name,
                status="running",
                phase=phase,
                pid=os.getpid(),
                proc_start=proc_start(os.getpid()),
                started_at=now(),
                progress={},
                error=None,
            )
            try:
                yield
                self.update(name, status="idle", phase="done", finished_at=now(), pid=None, proc_start=None)
            except BaseException as exc:
                self.update(
                    name,
                    status="cancelled" if self.cancelled else "failed",
                    phase=phase,
                    error=str(exc),
                    finished_at=now(),
                    pid=None,
                    proc_start=None,
                )
                raise
            finally:
                self.current = None

    def signal_handler(self, *_):
        self.cancelled = True
        if self.child and self.child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.child.pid, signal.SIGTERM)

    def log(self, name, text):
        directory = self.folder(name) / "logs"
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (dt.datetime.now().strftime("%Y-%m-%d") + ".log")
        # Bound daily log size and retain 30 days. Contents can contain filenames.
        if path.exists() and path.stat().st_size > 8 * 1024 * 1024:
            return
        with path.open("a", encoding="utf-8") as out:
            os.chmod(path, 0o600)
            out.write(f"{now()} {text.rstrip()}\n")
        cutoff = time.time() - 30 * 86400
        for old in directory.glob("*.log"):
            if old.stat().st_mtime < cutoff:
                old.unlink()

    def logs(self, name):
        files = sorted((self.folder(name) / "logs").glob("*.log"))[-3:]
        return "\n".join(p.read_text()[-256000:] for p in files)

    def _environment(self, dest):
        # External rustic environment must not override explicit application configuration.
        env = {k: v for k, v in os.environ.items() if not k.startswith("RUSTIC_")}
        if dest.get("env_file"):
            values = read_json(expand(dest["env_file"]))
            if not isinstance(values, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()
            ):
                raise Error(tr("env_file muss ein JSON-Objekt mit Zeichenketten enthalten."))
            env.update(values)
        env.update(dest.get("env", {}))
        return env

    def _profile(self, dest, repository=None):
        repo = repository or dest["repository"]
        if ":" not in repo:
            repo = str(expand(repo))
        lines = ["[repository]", "repository = " + json.dumps(repo, ensure_ascii=False)]
        if "password_command" in dest:
            lines.append("password-command = " + json.dumps(dest["password_command"], ensure_ascii=False))
        elif self.password_mode(dest) == "none":
            # An explicit empty credential is supported by rustic. Omitting it
            # would make a noninteractive timer try to prompt on /dev/null.
            lines.append('password = ""')
        else:
            key = self.password_path(dest)
            if not key.is_file():
                raise Error(tr("Die ausdrücklich konfigurierte Passwortdatei fehlt. Bitte wiederherstellen oder den Pfad korrigieren."))
            if key.stat().st_mode & 0o077:
                raise Error(tr("Schlüsseldatei ist zu offen. Bitte chmod 600 {p0}", p0=key))
            lines.append("password-file = " + json.dumps(str(key), ensure_ascii=False))
        if dest.get("options"):
            lines.append("[repository.options]")
            lines.extend(
                json.dumps(k, ensure_ascii=False) + " = " + json.dumps(v, ensure_ascii=False)
                for k, v in dest["options"].items()
            )
        return "\n".join(lines) + "\n"

    def run(self, name, args, *, dry_run=False, capture=True, progress=False, timeout=120, hook=None):
        if self.cancelled:
            raise Error(tr("Vorgang abgebrochen."))
        dest = self.dest(name)
        self.folder(name)
        if not hook and not dry_run and name not in self.prepared:
            self.prepared.add(name)
            if dest.get("pre_command"):
                self.run(
                    name,
                    [],
                    capture=False,
                    timeout=dest.get("hook_timeout", self.config.get("hook_timeout", 120)),
                    hook=dest["pre_command"],
                )
        env = self._environment(dest)
        secrets = [
            v
            for k, v in env.items()
            if any(x in k.upper() for x in ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY")) and v
        ]
        if "password_command" not in dest and self.password_path(dest).exists():
            secrets.append(self.show_key(name))
        secrets.extend(
            v
            for k, v in dest.get("options", {}).items()
            if any(x in k.upper() for x in ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY")) and v
        )

        def redact(text):
            for secret in secrets:
                if secret:
                    text = text.replace(secret, "***")
            return re.sub(r"(://)[^/@]+@", r"\1***@", text)

        with contextlib.ExitStack() as access:
            tmp = access.enter_context(tempfile.TemporaryDirectory(prefix="profile-", dir=self.folder(name)))
            profile = Path(tmp) / "engine.toml"
            inherited = ()
            if hook:
                command = ["/bin/sh", "-c", hook]
            else:
                repository = dest["repository"]
                if is_smb(repository):
                    try:
                        repository, inherited = access.enter_context(repository_access(repository))
                    except NetworkError as exc:
                        raise Error(str(exc)) from exc
                    if args and args[0] == "backup" and "--glob-file" in args:
                        # Protect the NAS mount even when it was first connected by this process.
                        globs = Path(args[args.index("--glob-file") + 1])
                        patterns = globs.read_text()
                        for _, root in kio_mounts():
                            literal = re.sub(r"([\\*?\[\]{}!])", r"\\\1", str(root))
                            patterns += "\n!" + literal + "\n!" + literal.rstrip("/") + "/**\n"
                        atomic(globs, patterns)
                if self.cancelled:
                    raise Error(tr("Vorgang abgebrochen."))
                atomic(profile, self._profile(dest, repository))
                binary = shutil.which(self.config.get("rustic_binary", "rustic"))
                if not binary:
                    raise Error(tr("rustic wurde nicht gefunden. Bitte rustic installieren."))
                command = [binary, "-P", str(profile)]
                command += (
                    ["--json-progress", "--progress-interval", "500ms"] if progress else ["--no-progress"]
                )
                if dry_run:
                    command.append("--dry-run")
                command += args
            self.child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
                pass_fds=inherited,
            )
            output = bytearray()
            tail = ""
            warned = False
            started = time.monotonic()
            aborted_at = None
            pending = {"out": b"", "err": b""}
            try:
                with selectors.DefaultSelector() as sel:
                    sel.register(self.child.stdout, selectors.EVENT_READ, "out")
                    sel.register(self.child.stderr, selectors.EVENT_READ, "err")
                    while sel.get_map():
                        if timeout and time.monotonic() - started > timeout:
                            raise Error(tr("Zeitlimit überschritten; Ziel möglicherweise nicht erreichbar."))
                        if self.cancelled:
                            if aborted_at is None:
                                aborted_at = time.monotonic()
                                with contextlib.suppress(ProcessLookupError):
                                    os.killpg(self.child.pid, signal.SIGTERM)
                            elif time.monotonic() - aborted_at > 5:
                                with contextlib.suppress(ProcessLookupError):
                                    os.killpg(self.child.pid, signal.SIGKILL)
                        for key, _ in sel.select(0.2):
                            block = os.read(key.fileobj.fileno(), 65536)
                            stream = key.data
                            if not block:
                                sel.unregister(key.fileobj)
                                block = b"\n"  # flush an unterminated final line
                            elif stream == "out" and capture:
                                output.extend(block)
                                if len(output) > MAX_OUTPUT:
                                    raise Error(
                                        tr("Ausgabe zu groß (32 MiB). Es werden keine unvollständigen Listen angezeigt.")
                                    )
                            pending[stream] += block
                            if len(pending[stream]) > MAX_OUTPUT:
                                raise Error(tr("Einzelne Ausgabezeile zu groß."))
                            lines = pending[stream].split(b"\n")
                            pending[stream] = lines.pop()
                            for raw in lines:
                                text = redact(raw.decode("utf-8", "replace"))
                                if not text:
                                    continue
                                if stream == "err":
                                    tail = (tail + "\n" + text)[-6000:]
                                    warned |= "[WARN]" in text or "[ERROR]" in text
                                    self.log(name, text)
                                elif progress:
                                    try:
                                        event = json.loads(text)
                                    except ValueError:
                                        self.log(name, text)
                                        continue
                                    if isinstance(event, dict):
                                        warned |= event.get("message_type") in ("error", "exit_error")
                                        self.update(name, progress=event)
                                elif not capture:
                                    self.log(name, text)
                code = self.child.wait()
                if self.cancelled:
                    raise Error(tr("Vorgang abgebrochen."))
                if code:
                    raise Error(tail.strip() or tr("Befehl fehlgeschlagen (Exit {p0}).", p0=code))
                return output.decode("utf-8"), warned
            finally:
                if self.child.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(self.child.pid, signal.SIGKILL)
                    self.child.wait()
                self.child.stdout.close()
                self.child.stderr.close()
                self.child = None

    def snapshots(self, name):
        raw, _ = self.run(name, ["snapshots", "--json"])
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError(tr("keine Liste"))
            result = []
            for item in data:
                result.extend(item["snapshots"] if "snapshots" in item else [item])
            for snapshot in result:
                safe_snapshot(snapshot["id"])
            return sorted(result, key=lambda x: x["time"], reverse=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise Error(tr("Unerwartete Snapshot-Ausgabe von rustic.")) from exc

    def ls(self, name, snapshot, path):
        snapshot, path = safe_snapshot(snapshot), safe_path(path)
        raw, _ = self.run(name, ["cat", "tree", f"{snapshot}:{path}"])
        try:
            nodes = json.loads(raw)["nodes"] or []
            result = []
            for node in nodes:
                filename = node["name"]
                if (
                    not isinstance(filename, str)
                    or filename in (".", "..")
                    or "/" in filename
                    or "\0" in filename
                ):
                    raise ValueError(tr("ungültiger Dateiname"))
                result.append({**node, "path": str(PurePosixPath(path) / filename)})
            return sorted(result, key=lambda x: (x["type"] != "dir", x["name"].casefold()))
        except (KeyError, TypeError, ValueError) as exc:
            raise Error(tr("Unerwartete Verzeichnis-Ausgabe von rustic.")) from exc

    def refresh_stats(self, name):
        snapshots = self.snapshots(name)
        raw, _ = self.run(name, ["repoinfo", "--json", "--only-files"])
        try:
            size = sum(x["size"] for x in json.loads(raw)["files"]["repo"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Error(tr("Unerwartete Repository-Statistik.")) from exc
        self.update(name, snapshot_count=len(snapshots), repository_bytes=size, stats_updated=now())

    def initialize(self, name):
        with self.operation(name, "init"):
            self.run(name, ["init"], capture=False, timeout=None)
            self.remember_initialized(name)

    def check(self, name):
        with self.operation(name, "check"):
            _, warned = self.run(name, ["check"], capture=False, progress=True, timeout=None)
            if warned:
                raise Error(tr("rustic meldete Warnungen bei der Prüfung; siehe Protokoll."))
            self.update(name, last_check=now())

    def backup(self, name, dry_run=False):
        dest = self.dest(name)
        with self.operation(name, "dry-run" if dry_run else "backup"):
            try:
                sources = self.config.get("source", "~")
                sources = [sources] if isinstance(sources, str) else sources
                sources = [str(expand(s)) for s in sources]
                for source in sources:
                    if not Path(source).exists():
                        raise Error(tr("Backup-Quelle fehlt: {p0}", p0=source))
                args = ["backup", "--json", "--label", APP]
                if not dry_run:
                    args.append("--init")  # rustic leaves existing repositories intact.
                exclude = self.config_dir / self.config.get("exclude_file", "excludes.txt")
                if exclude.exists():
                    patterns = exclude.read_text()
                elif "exclude_file" in self.config:
                    raise Error(tr("Ausschlussdatei fehlt: {p0}", p0=exclude))
                else:
                    patterns = ""
                # Avoid backing up the repository, keys, live state and restored copies.
                exclusions = [
                    self.config_dir / "keys",
                    self.state_dir,
                    Path.home() / "Restored",
                    Path.home() / ".cache/rustic",
                ]
                exclusions.extend(root for _, root in kio_mounts())
                for destination in self.config["destinations"]:
                    if ":" not in destination["repository"]:
                        exclusions.append(expand(destination["repository"]).resolve())
                    if "password_command" not in destination:
                        password = self.password_path(destination)
                        exclusions.extend([password, password.with_name(password.name + ".pending")])
                    if destination.get("env_file"):
                        exclusions.append(expand(destination["env_file"]))
                for path in exclusions:
                    # Escape literal metacharacters in filesystem names.
                    literal = re.sub(r"([\\*?\[\]{}!])", r"\\\1", str(path))
                    # Also prune descendants when a protected directory is itself
                    # an explicit source. Otherwise rustic may stat live temporary
                    # status files before excluding them and report a spurious warning.
                    patterns += "\n!" + literal + "\n!" + literal.rstrip("/") + "/**\n"
                args.extend(["--", *sources])
                # Internal exclusions go last so user includes cannot re-add keys
                # or the backup repository itself.
                with tempfile.TemporaryDirectory(prefix="excludes-", dir=self.folder(name)) as tmp:
                    glob_file = Path(tmp) / "exclude-globs.txt"
                    atomic(glob_file, patterns)
                    args[1:1] = ["--glob-file", str(glob_file)]
                    _, warned = self.run(
                        name, args, capture=False, progress=True, dry_run=dry_run, timeout=None
                    )
                if warned:
                    raise Error(
                        tr("rustic meldete Warnungen. Sicherung gilt nicht als vollständig; Aufbewahrung wurde nicht ausgeführt. Siehe Protokoll.")
                    )
                if dry_run:
                    return {"ok": True, "dry_run": True}
                if not self.state(name).get("progress", {}).get("snapshot_id"):
                    raise Error(
                        tr("rustic bestätigte keinen neuen Snapshot. Bitte Version und Protokoll prüfen.")
                    )
                stamp = now()
                self.update(name, last_success=stamp, last_backup_status="success", backup_error=None)
                self.remember_initialized(name)
                retention = dest.get("retention", self.config.get("retention", RETENTION))
                self.update(name, phase="retention")
                retention_args = ["forget", "--prune", "--filter-label", APP]
                for key, value in retention.items():
                    retention_args.extend(["--keep-" + key, str(value)])
                try:
                    _, warned = self.run(name, retention_args, capture=False, timeout=None)
                    if warned:
                        raise Error(tr("rustic meldete Warnungen bei der Bereinigung; siehe Protokoll."))
                    self.update(name, maintenance_error=None)
                except Error as exc:
                    if self.cancelled:
                        raise
                    self.log(name, tr("Aufbewahrung fehlgeschlagen: {p0}", p0=exc))
                    self.update(name, maintenance_error=str(exc))
                try:
                    self.refresh_stats(name)
                except Error as exc:
                    if self.cancelled:
                        raise
                    self.log(name, tr("Statistik nicht aktualisiert: {p0}", p0=exc))
                return {"ok": True, "last_success": stamp}
            except BaseException as exc:
                if not dry_run:
                    self.update(
                        name,
                        last_backup_status="cancelled" if self.cancelled else "failed",
                        last_failure=now(),
                        backup_error=str(exc),
                    )
                    if not self.cancelled:
                        self.notify(tr("Backup fehlgeschlagen"), dest.get("display_name", name))
                        if dest.get("on_failure_command"):
                            with contextlib.suppress(Exception):
                                self.run(
                                    name,
                                    [],
                                    capture=False,
                                    timeout=dest.get("hook_timeout", self.config.get("hook_timeout", 120)),
                                    hook=dest["on_failure_command"],
                                )
                raise

    @staticmethod
    def notify(title, message, path=None):
        if not shutil.which("notify-send"):
            return
        args = ["notify-send", "--app-name", "CachyOS Time Machine", "--icon", "document-revert"]
        if path:
            # Detached notification waits for a click without blocking CLI or timer.
            args += ["--action", tr("open=In Dolphin öffnen"), "--wait", "--expire-time", "10000"]
            script = "import subprocess,sys; r=subprocess.run(sys.argv[2:],capture_output=True,text=True); subprocess.Popen(['xdg-open',sys.argv[1]]) if r.stdout.strip()=='open' else None"
            subprocess.Popen(
                [sys.executable, "-c", script, str(path), *args, title, message],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            subprocess.run(
                [*args, title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )

    def restore(self, name, snapshot, path, target=None):
        snapshot, path = safe_snapshot(snapshot), safe_path(path)
        # Always allocate a new private directory, even with --target. Never restore in place.
        base = expand(target) if target else Path.home() / "Restored"
        base.mkdir(parents=True, exist_ok=True)
        folder = base / (dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_") + uuid.uuid4().hex[:8])
        folder.mkdir(mode=0o700)
        item = folder / path.lstrip("/")
        item.parent.mkdir(parents=True, exist_ok=True)
        with self.operation(name, "restore"):
            self.run(
                name,
                ["restore", "--", f"{snapshot}:{path}", str(item)],
                capture=False,
                progress=True,
                timeout=None,
            )
            self.update(name, last_restored=str(item))
        self.notify(tr("Wiederherstellung abgeschlossen"), str(item), item if item.is_dir() else item.parent)
        return {"ok": True, "target": str(folder), "restored": str(item)}

    def install_timers(self, enable=True):
        directory = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"
        directory.mkdir(parents=True, exist_ok=True)
        units = []
        # Validate every calendar before changing any unit.
        for dest in self.config["destinations"]:
            if dest.get("schedule"):
                result = subprocess.run(
                    ["systemd-analyze", "calendar", dest["schedule"]], capture_output=True, text=True
                )
                if result.returncode:
                    raise Error(tr("Ungültiger Zeitplan für {p0}: {p1}", p0=dest['name'], p1=result.stderr))
        command = [
            sys.executable,
            "-m",
            "timemachine.cli",
            "--config-dir",
            str(self.config_dir),
            "--state-dir",
            str(self.state_dir),
            "backup",
            "--dest",
        ]

        # systemd command escaping differs from shell escaping: escape % specifiers and quotes.
        def unit_arg(arg):
            return (
                '"'
                + str(arg).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
                + '"'
            )

        root = str(Path(__file__).resolve().parent.parent)
        wanted = set()
        for dest in self.config["destinations"]:
            if not dest.get("schedule"):
                continue
            stem = APP + "-" + dest["name"]
            wanted.add(stem + ".timer")
            service = (
                "[Unit]\nDescription=CachyOS Time Machine backup\n\n[Service]\nType=oneshot\nEnvironment="
                + unit_arg("PYTHONPATH=" + root)
                + "\nExecStart="
                + " ".join(unit_arg(x) for x in [*command, dest["name"]])
                + "\nTimeoutStartSec=infinity\nTimeoutStopSec=15\nKillMode=control-group\nNice=10\nIOSchedulingClass=best-effort\nIOSchedulingPriority=7\n"
            )
            timer = (
                "[Unit]\nDescription=CachyOS Time Machine schedule\n\n[Timer]\nOnCalendar="
                + dest["schedule"].replace("%", "%%")
                + "\nPersistent=true\nAccuracySec=1min\nUnit="
                + stem
                + ".service\n\n[Install]\nWantedBy=timers.target\n"
            )
            atomic(directory / (stem + ".service"), service)
            atomic(directory / (stem + ".timer"), timer)
            units.append(stem + ".timer")
        for old in directory.glob(APP + "-*.timer"):
            if old.name not in wanted:
                subprocess.run(
                    ["systemctl", "--user", "disable", "--now", old.name], check=True, capture_output=True
                )
                old.unlink()
                old.with_suffix(".service").unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        if units:
            subprocess.run(
                ["systemctl", "--user", "enable" if enable else "disable", "--now", *units],
                check=True,
                capture_output=True,
            )
            if enable:
                subprocess.run(["systemctl", "--user", "restart", *units], check=True, capture_output=True)
        atomic(self.state_dir / "timers.json", {"enabled": enable, "units": units, "updated_at": now()})
        return {"ok": True, "timers": units, "enabled": enable}
