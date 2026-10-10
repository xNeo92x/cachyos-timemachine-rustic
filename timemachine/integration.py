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
        + "Comment=Start the backup service when logging into KDE\n"
        + "Comment[de]=Backup-Dienst bei der KDE-Anmeldung starten\nExec="
        + desktop_arg(launcher or launcher_path())
        + " service\nIcon=cachyos-time-machine\nTerminal=false\nOnlyShowIn=KDE;\n"
        + "X-KDE-autostart-after=panel\nHidden="
        + ("false" if enabled else "true")
        + "\n"
    )


def panel_script(remove=False):
    """Enable in existing trays, supporting both legacy and merged Plasma containments."""
    return """
var plugin = 'org.cachyos.timemachine';
var removing = %s;
var integrated = false;
var ps = panels();
var standalone = [];
function items(tray, key) {
    var value = tray.readConfig(key, []);
    return Array.isArray(value) ? value : String(value || '').split(',').filter(function(v) { return v.length > 0; });
}
function change(tray, key, enabled) {
    var values = items(tray, key);
    var next = values.filter(function(v) { return v !== plugin; });
    if (enabled) next.push(plugin);
    if (JSON.stringify(values) !== JSON.stringify(next)) tray.writeConfig(key, next);
}
for (var i = 0; i < ps.length; ++i) {
    var ws = ps[i].widgets();
    for (var j = 0; j < ws.length; ++j) {
        var widget = ws[j];
        if (widget.type === plugin) standalone.push(widget);
        if (widget.type === 'org.kde.plasma.systemtray') {
            widget.currentConfigGroup = [];
            var legacyId = widget.readConfig('SystrayContainmentId', 0);
            var tray = legacyId ? desktopById(legacyId) : widget;
            if (!tray) continue;
            tray.currentConfigGroup = ['General'];
            change(tray, 'knownItems', !removing);
            change(tray, 'shownItems', !removing);
            change(tray, 'hiddenItems', false);
            change(tray, 'extraItems', !removing);
            tray.reloadConfig();
            integrated = true;
        }
    }
}
// Migrate 0.2.0's separate right-hand panel widget only after a tray was found.
if (integrated || removing) standalone.forEach(function(widget) { widget.remove(); });
print(integrated || removing ? 'CACHYOS_TRAY_OK' : 'CACHYOS_TRAY_MISSING');
""" % ("true" if remove else "false",)


def integrate_panel(remove=False):
    from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

    shell = QDBusInterface(
        "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", QDBusConnection.sessionBus()
    )
    if not shell.isValid():
        return False
    reply = shell.call("evaluateScript", panel_script(remove))
    return reply.type() != QDBusMessage.MessageType.ErrorMessage and any(
        "CACHYOS_TRAY_OK" in str(value) for value in reply.arguments()
    )


def reload_dbus_services():
    """Refresh session-bus activation after creating a previously absent services directory."""
    from PySide6.QtDBus import QDBusConnection, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    request = QDBusMessage.createMethodCall(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ReloadConfig"
    )
    return bus.call(request, timeout=3000).type() != QDBusMessage.MessageType.ErrorMessage
