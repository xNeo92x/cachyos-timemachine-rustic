"""SMB repositories selected in KDE, resolved afresh for every rustic process."""

import contextlib
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from .i18n import tr


class NetworkError(RuntimeError):
    pass


def is_smb(repository):
    return repository.lower().startswith("smb:")


def smb_url(value, *, identity=False):
    """Canonical, password-free URL; identity ignores users sharing one repository."""
    try:
        url = urlsplit(value)
        path = unquote(url.path).rstrip("/")
        if (
            url.scheme != "smb"
            or not url.hostname
            or not path.startswith("/")
            or not path.strip("/")
            or any(part in (".", "..") for part in path.split("/"))
            or url.query
            or url.fragment
            or any(c in unquote(value) for c in "\r\n\0")
        ):
            raise ValueError
        if url.password is not None:
            raise NetworkError(tr("NAS-Passwörter bitte in KDE Wallet speichern, nicht in der SMB-Adresse."))
        host = url.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        if url.port and url.port != 445:
            host += ":" + str(url.port)
        if url.username and not identity:
            host = quote(unquote(url.username), safe=";") + "@" + host
        return urlunsplit(("smb", host, quote(path, safe="/"), "", ""))
    except ValueError as exc:
        raise NetworkError(tr("Bitte einen NAS-Ordner wählen: smb://server/freigabe/backup-ordner")) from exc


def kio_call(member, value):
    # Lazy import: local/other rustic backends need neither Qt nor a desktop session.
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusConnection, QDBusMessage

    app = QCoreApplication.instance() or QCoreApplication([])
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise NetworkError(tr("NAS-Zugriff benötigt eine laufende KDE-Benutzersitzung (Sitzungs-D-Bus)."))
    message = QDBusMessage.createMethodCall(
        "org.kde.KIOFuse", "/org/kde/KIOFuse", "org.kde.KIOFuse.VFS", member
    )
    message.setArguments([value])
    reply = bus.call(message, timeout=120000 if member == "mountUrl" else 5000)
    # Keep the application alive throughout the synchronous call.
    _ = app
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        detail = re.sub(r"(://)[^/@]+@", r"\1***@", reply.errorMessage())
        raise NetworkError(
            tr("NAS nicht erreichbar. Freigabe in Dolphin öffnen und Zugang in KDE Wallet speichern. Benötigte Pakete: kio-fuse und kio-extras. ") + detail
        )
    args = reply.arguments()
    if len(args) != 1 or not isinstance(args[0], str) or not args[0]:
        raise NetworkError(tr("KDE hat keinen gültigen NAS-Pfad zurückgegeben."))
    return args[0]


def kio_mounts():
    """Read actual FUSE mounts, never infer connectivity from an existing directory."""
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        split = fields.index("-")
        kind, source = fields[split + 1:split + 3]
        if kind == "fuse.kio-fuse" or (kind == "fuse" and source == "kio-fuse"):
            mountpoint = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])
            mounts.append((fields[0], Path(mountpoint)))
    return mounts


def mounted_url(path):
    """Convert a picker-returned local KIO path back into its persistent URL."""
    path = Path(path).absolute()
    if any(path.is_relative_to(root) for _, root in kio_mounts()):
        return smb_url(kio_call("remoteUrl", str(path)))
    return None


@contextlib.contextmanager
def repository_access(repository):
    """Pin the connected directory so an unmount cannot redirect writes to local disk."""
    url = smb_url(repository)
    path = Path(kio_call("mountUrl", url))
    if not path.is_absolute():
        raise NetworkError(tr("KDE hat keinen absoluten NAS-Pfad zurückgegeben."))
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        info = Path(f"/proc/self/fdinfo/{fd}").read_text()
        mount_id = re.search(r"^mnt_id:\s*(\d+)$", info, re.MULTILINE)
        if not mount_id or not any(mount_id[1] == ident for ident, _ in kio_mounts()):
            raise NetworkError(tr("NAS ist nicht als KDE-Netzwerkdateisystem verbunden; Vorgang abgebrochen."))
        # Use the inherited directory descriptor, rather than a volatile /run/user path.
        yield f"/proc/self/fd/{fd}", (fd,)
    except OSError as exc:
        raise NetworkError(tr("NAS-Verzeichnis nicht verfügbar; es wird kein lokales Ersatz-Backup angelegt.")) from exc
    finally:
        if fd is not None:
            os.close(fd)
