#!/usr/bin/env python3
"""User-local installer. No sudo, network access or package installation."""

import argparse
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

APP = "cachyos-time-machine"


def main():
    parser = argparse.ArgumentParser(description="Install/update CachyOS Time Machine for the current user")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument(
        "--bin-dir", type=Path, default=Path.home() / ".local/bin", help="Custom launcher directory"
    )
    args = parser.parse_args()
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    app_dir = data / APP
    launcher = args.bin_dir.absolute() / APP
    desktop = data / "applications" / (APP + ".desktop")
    autostart = config / "autostart" / (APP + ".desktop")
    units = config / "systemd/user"
    if args.uninstall:
        timers = [p.name for p in units.glob(APP + "-*.timer")]
        if timers:
            subprocess.run(["systemctl", "--user", "disable", "--now", *timers], check=True)
        for pattern in (APP + "-*.timer", APP + "-*.service"):
            for path in units.glob(pattern):
                path.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        launcher.unlink(missing_ok=True)
        desktop.unlink(missing_ok=True)
        autostart.unlink(missing_ok=True)
        icon = data / "icons/hicolor/scalable/apps" / (APP + ".svg")
        icon.unlink(missing_ok=True)
        if app_dir.exists():
            shutil.rmtree(app_dir)
        print(
            "Anwendung und Zeitpläne entfernt. Konfiguration, Schlüssel, Protokolle und Backups bleiben erhalten."
        )
        return 0
    if importlib.util.find_spec("PySide6") is None or shutil.which("rustic") is None:
        print("Bitte zuerst installieren: sudo pacman -Syu python-pyside6 rustic libnotify", file=sys.stderr)
        return 1
    version = subprocess.run(["rustic", "--version"], text=True, capture_output=True, check=True).stdout
    import re

    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (0, 11, 4):
        print("rustic >= 0.11.4 erforderlich. Bitte System aktualisieren.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent
    app_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        root / "timemachine",
        app_dir / "timemachine",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("README.md", "LICENSE"):
        shutil.copy2(root / name, app_dir / name)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    # Python path is absolute so both desktop entries and systemd work outside the checkout.
    script = (
        "#!/bin/sh\nexport PYTHONPATH="
        + shlex.quote(str(app_dir))
        + '\nif [ "$#" -eq 0 ]; then set -- gui; fi\nexec '
        + shlex.quote(sys.executable)
        + ' -m timemachine.cli "$@"\n'
    )
    launcher.write_text(script)
    launcher.chmod(0o755)

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

    entry = (
        "[Desktop Entry]\nType=Application\nName=CachyOS Time Machine\nComment=Encrypted backups with rustic\nComment[de]=Verschlüsselte Sicherungen mit rustic\nExec="
        + desktop_arg(launcher)
        + " gui\nIcon="
        + APP
        + "\nTerminal=false\nCategories=System;Utility;Archiving;\nStartupNotify=false\n"
    )
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(entry)
    autostart.parent.mkdir(parents=True, exist_ok=True)
    autostart.write_text(entry.replace(" gui\n", " gui --tray\n") + "X-KDE-autostart-after=panel\n")
    icon_dir = data / "icons/hicolor/scalable/apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "packaging" / (APP + ".svg"), icon_dir)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(desktop.parent)], check=False)
    print("Installiert. Start: " + str(launcher))
    print("Beim nächsten KDE-Login erscheint das Symbol im Systemabschnitt.")
    print("Vorhandene Zeitpläne nach einem Update neu schreiben: " + str(launcher) + " install")
    return 0


if __name__ == "__main__":
    sys.exit(main())
