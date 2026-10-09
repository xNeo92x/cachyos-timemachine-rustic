"""User desktop integration shared by installer, Plasma and configuration dialog."""

import os
import shutil
from pathlib import Path

APP = "cachyos-time-machine"
PLUGIN = "org.cachyos.timemachine"
SERVICE = "org.cachyos.TimeMachine"
OBJECT = "/TimeMachine"


def desktop_arg(value):
    return (
        '"'
        + str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
        .replace("%", "%%")
        + '"'
    )


def launcher_path():
    local = Path.home() / ".local/bin" / APP
    return str(local) if local.exists() else shutil.which(APP) or APP


def autostart_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / (APP + ".desktop")


def autostart_enabled():
    path = autostart_path()
    return path.exists() and "Hidden=true" not in path.read_text()


def set_autostart(enabled, launcher=None):
    path = autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\nType=Application\nName=CachyOS Time Machine\n"
        + "Comment[de]=Backup-Dienst bei der KDE-Anmeldung starten\nExec="
        + desktop_arg(launcher or launcher_path())
        + " service\nIcon=cachyos-time-machine\nTerminal=false\nOnlyShowIn=KDE;\n"
        + "X-KDE-autostart-after=panel\nHidden="
        + ("false" if enabled else "true")
        + "\n"
    )


def panel_script(remove=False):
    """Add at most one widget to an existing panel; never replace the user's layout."""
    return """
var found = false;
var ps = panels();
for (var i = 0; i < ps.length; ++i) {
    var ws = ps[i].widgets();
    for (var j = 0; j < ws.length; ++j) {
        if (ws[j].type === 'org.cachyos.timemachine') {
            found = true;
            %s
        }
    }
}
%s
""" % (
        "ws[j].remove();" if remove else "",
        "" if remove else "if (!found && ps.length) ps[0].addWidget('org.cachyos.timemachine');",
    )


def integrate_panel(remove=False):
    from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

    shell = QDBusInterface(
        "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", QDBusConnection.sessionBus()
    )
    if not shell.isValid():
        return False
    reply = shell.call("evaluateScript", panel_script(remove))
    return reply.type() != QDBusMessage.MessageType.ErrorMessage
