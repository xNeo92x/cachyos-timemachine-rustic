"""Public CLI, also used by the GUI and systemd timers."""

import argparse
import getpass
import json
import signal
import subprocess
import sys

from .core import Engine, Error


def parser():
    p = argparse.ArgumentParser(description="CachyOS Time Machine · rustic backups for KDE")
    p.add_argument("--config-dir")
    p.add_argument("--state-dir")
    sub = p.add_subparsers(dest="command", required=True)
    gui = sub.add_parser("gui")
    gui.add_argument("--tray", action="store_true", help="Compatibility alias for the session service")
    gui.add_argument("--window", action="store_true", help="Open the optional classic Qt window")
    sub.add_parser("service")
    auto = sub.add_parser("autostart")
    auto.add_argument("action", choices=["enable", "disable", "status"])
    sub.add_parser("configure")
    for cmd in ("status", "destinations"):
        sub.add_parser(cmd).add_argument("--json", action="store_true")
    for cmd in ("init", "backup", "check", "snapshots", "ls", "restore", "cancel", "log", "stats"):
        c = sub.add_parser(cmd)
        c.add_argument("--dest", required=True)
        c.add_argument("--json", action="store_true")
        if cmd == "backup":
            c.add_argument("--dry-run", action="store_true")
        if cmd in ("ls", "restore"):
            c.add_argument("--snapshot", required=True)
            c.add_argument("--path", required=True)
        if cmd == "restore":
            c.add_argument("--target", help="Parent directory; creates a new subfolder on every restore")
    sub.add_parser("install")
    sub.add_parser("pause")
    c = sub.add_parser("key")
    c.add_argument("action", choices=["set", "show", "save-1password"])
    c.add_argument("--dest", required=True)
    c.add_argument("--vault", help="1Password vault for save-1password")
    c.add_argument("--stdin", action="store_true", help="Read password from stdin instead of prompting")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "gui":
            if args.window:
                from .gui import main as gui_main

                return gui_main(args.config_dir, args.state_dir)
            from .service import main as service_main
            from .service import request_popup

            return (
                service_main(args.config_dir, args.state_dir)
                if args.tray
                else request_popup(args.config_dir, args.state_dir)
            )
        if args.command == "service":
            from .service import main as service_main

            return service_main(args.config_dir, args.state_dir)
        if args.command == "autostart":
            from .integration import autostart_enabled, set_autostart

            if args.action != "status":
                set_autostart(args.action == "enable")
            print(json.dumps({"ok": True, "enabled": autostart_enabled()}))
            return 0
        if args.command == "configure":
            print(Engine.create_config(args.config_dir))
            return 0
        engine = Engine(args.config_dir, args.state_dir)
        signal.signal(signal.SIGTERM, engine.signal_handler)
        signal.signal(signal.SIGINT, engine.signal_handler)
        cmd = args.command
        result = {"ok": True}
        if cmd in ("status", "destinations"):
            result["destinations"] = engine.status()
        elif cmd == "key":
            if args.action == "set":
                password = (
                    sys.stdin.readline().rstrip("\n") if args.stdin else getpass.getpass("Backup-Passwort: ")
                )
                if not args.stdin and getpass.getpass("Wiederholen: ") != password:
                    raise Error("Passwörter stimmen nicht überein.")
                engine.set_key(args.dest, password)
            elif args.action == "show":
                print(engine.show_key(args.dest))
                return 0
            else:
                engine.save_1password(args.dest, args.vault)
        elif cmd == "init":
            engine.initialize(args.dest)
        elif cmd == "backup":
            result = engine.backup(args.dest, args.dry_run)
        elif cmd == "check":
            engine.check(args.dest)
        elif cmd == "snapshots":
            result["snapshots"] = engine.snapshots(args.dest)
        elif cmd == "ls":
            result["entries"] = engine.ls(args.dest, args.snapshot, args.path)
        elif cmd == "restore":
            result = engine.restore(args.dest, args.snapshot, args.path, args.target)
        elif cmd == "cancel":
            engine.cancel(args.dest)
        elif cmd == "log":
            text = engine.logs(args.dest)
            if not args.json:
                print(text)
                return 0
            result["log"] = text
        elif cmd == "stats":
            with engine.operation(args.dest, "stats"):
                engine.refresh_stats(args.dest)
        elif cmd in ("install", "pause"):
            result = engine.install_timers(cmd == "install")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
