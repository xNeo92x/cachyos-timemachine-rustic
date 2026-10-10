# CachyOS Time Machine · rustic

[Deutsch](README.md) | **English**

File history for CachyOS KDE, inspired by
[Omarchy Time Machine](https://github.com/jankeesvw/omarchy-time-machine).
**[rustic](https://github.com/rustic-rs/rustic)** handles all backup operations.
The default interface is a **native Plasma 6 applet**: clicking its panel icon
opens a **popup anchored to the KDE panel**. Status, backup actions and the
snapshot file browser appear there, without a separate main window. Plasma
handles positioning, theme and popup behavior, including on Wayland.
A Python/PySide6 service connects the applet to the rustic CLI over the session
D-Bus. Settings, password management and logs use Qt dialogs.

## Features

- A panel icon with a status dot: red for errors or overdue backups, blue during
  operations, and orange when setup is required.
- Multiple destinations with individual schedules, passwords, status and logs.
- Automatic backups using persistent systemd user timers; manual backups from
  the Plasma popup or terminal.
- Optional startup when logging into KDE, configurable in the popup and Settings.
  KDE can also start the service on demand through D-Bus.
- Encrypted, deduplicated, incremental backups; each snapshot is a fully
  restorable version of your files.
- Local/external drives, NAS, SFTP, S3, REST, rclone and other rustic backends.
- Choose NAS folders in KDE's network dialog; SMB URLs reconnect through KIO FUSE
  before every operation, including scheduled backups.
- Multiple sources, exclusion patterns and configurable retention.
- Progress, cancellation, integrity checks, dry runs and offline status.
- Snapshot browser with date selection, folder navigation and a text filter.
  Changing the date preserves the current path.
- Restore individual files or entire folders to new directories under
  `~/Restored`, without overwriting current files.
- Desktop notifications and opening restored files in Dolphin.
- Password file or external password command; optional 1Password export.
- Preparation and failure hooks; logs retained for 30 days.
- German and English interfaces; system language by default, changeable in Settings.

## Interface language

Open **Settings → Sources & destinations → Language** and choose **Use system
language**, **Deutsch**, or **English**. System language is the default: German
on German systems, English on English systems and as the fallback for other
languages. KDE language preferences (`LANGUAGE`) and locale settings are respected.

**Save** applies the language immediately to the Plasma popup and Qt dialogs;
changing language does not require logging out. The preference survives restarts.
Custom destination names, paths, exclusion patterns and schedules are preserved.
Existing logs and messages emitted by rustic itself keep their original language.

## Installing on CachyOS KDE

Requires KDE **Plasma >= 6.3**, Kirigami, Python >= 3.11, Qt/PySide6 >= 6.6,
and **rustic >= 0.11.4**. rustic and PySide6 are available in the Arch/CachyOS
repositories. The pacman package is **`pyside6`**, while the Python module is
named `PySide6`.

```bash
sudo pacman -Syu pyside6 rustic libnotify git plasma-workspace kirigami kio-fuse kio-extras kdialog &&
git clone https://github.com/xNeo92x/cachyos-timemachine-rustic.git &&
cd cachyos-timemachine-rustic &&
python install.py &&
~/.local/bin/cachyos-time-machine gui
```

The installer installs for your user and does not itself require sudo. It creates
the Plasma applet, application menu entry, D-Bus activation and a KDE autostart
entry. In a running KDE session it enables the icon in the existing **system
tray**, next to the other status icons and before the clock. A separate icon at
the right end of the panel from version 0.2.0 is automatically removed. Other
panel settings are preserved.

If KDE does not allow automatic integration, use **Configure System Tray →
Entries → CachyOS Time Machine → Always shown**. The SVG loads directly from
the applet rather than the icon theme cache. After updating the applet, log out
of KDE and back in: Plasma caches loaded QML components.

**Clicking the icon opens the popup.** It includes destination selection, backup,
check, dry run, cancellation, restore and scheduling. **Start automatically when
logging into KDE** controls the background service. Disabling it leaves the
applet and independent systemd backup schedules in place; the applet starts the
service on demand when needed. Updates preserve the selected autostart setting.

The applet can alternatively be added as a separate panel widget. The installer
and application menu entry use the system tray by default. The old Qt tray icon
is not created in the default mode.

### Starting immediately after installation

Version 0.2.1 refreshes D-Bus activation in the running session. If the session
bus still cannot find the new service file, `cachyos-time-machine gui` launches
the service directly and waits until it is ready. Logging back into KDE is not
required for this initial start. Actual startup failures are recorded in
`~/.local/state/cachyos-time-machine/desktop-service.log`, or the corresponding
state directory when using custom XDG paths.

An Arch package is also available as an alternative to user-local installation:

```bash
cd packaging
makepkg -si
```

After package installation, add the applet or run `cachyos-time-machine gui`,
then enable autostart in the popup. A PKGBUILD is included; this does not imply
that the package has been published to the AUR.

## First backup

1. Open **Settings** in the popup. Set sources and one or more destinations.
   Use **Choose files …** for multiple files or **Choose folder …** for folders.
   The repository folder chooser accepts local folders and mounted NAS/USB
   folders. You can create a dedicated backup folder in the file dialog.
   Replace the initial `CHANGE-ME` path. Remote backends retain their repository
   field and backend options.
2. Optional: open **Password …** and save a custom password. Keep an additional
   copy outside this PC, for example in a password manager. Skip this step to
   back up without a custom password.
3. Choose **Back up now**. A new repository is initialized automatically on its
   first backup, including when started by a schedule. **Initialize** remains
   available as an additional manual action.
4. Choose **Enable schedules**. Saving Settings also rewrites and enables the
   schedules; failures are displayed.

Without a saved password, the application uses the empty password supported by
rustic. No password prompt or password file is required. The repository format
remains encrypted, but an empty password provides **no password protection**:
anyone with access to the repository can read the backups. Existing repositories
with custom passwords still require their original password; they are not
reinitialized or changed to an empty password. An explicitly configured missing
`password_file` remains an error.

For a repository already used without a password by the application, **Password …**
can set a custom password later and replace the empty-password access. Existing
snapshots are preserved. Existing saved custom passwords are not overwritten.
If a password change fails, the new local `.pending` password file is retained
for recovery.

A saved password is stored by default in
`~/.config/cachyos-time-machine/keys/NAME.password`, with **0600** permissions.
It is excluded from backups and does not appear in command arguments or logs.
The local password file is not additionally encrypted by KWallet; it follows
the original application's unattended file-based model. `password_command` can
use an external password store if it is accessible without interaction in the
systemd user context.

## Configuration

`~/.config/cachyos-time-machine/config.json`:

```json
{
  "language": "system",
  "source": ["~"],
  "exclude_file": "excludes.txt",
  "stale_hours": 48,
  "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 3},
  "destinations": [
    {
      "name": "usb",
      "display_name": "My backup drive",
      "repository": "/run/media/YOUR-USER/Backup/rustic",
      "schedule": "*-*-* 03:00:00"
    }
  ]
}
```

`source` can also be a single string. All sources must exist, otherwise the
entire backup fails. Backups run as your normal user; for example, backing up
`/etc` includes only readable files. This is a file backup with version history,
not a bootable system image.

| Option | Meaning |
| --- | --- |
| `language` | Global interface language: `system` (default), `de`, or `en` |
| `name` | Unique destination name: letters/digits, `-` or `_` |
| `display_name` | Display name, defaults to `name` |
| `repository` | Local path or native rustic backend specification |
| `schedule` | systemd OnCalendar; empty/missing means manual only |
| `retention` | Global or per-destination retention; at least one positive count |
| `stale_hours` | Hours since the last successful backup before a warning; global or per destination |
| `pre_command` | Prepare the destination, e.g. start a mount service; also runs before browse/check/init |
| `on_failure_command` | Run after a failed backup |
| `hook_timeout` | Hook timeout in seconds, defaults to 120 |
| `password_file` | Alternative password file; requires 0600 permissions |
| `password_command` | Alternative rustic password command; cannot be combined with `password_file` |
| `options` | String values for rustic `[repository.options]` |
| `env_file` | Path to a JSON file containing environment variables for this destination |
| `env` | Environment variables defined directly for this destination |

Custom hook commands explicitly run through `/bin/sh -c` as your user. A dry
run executes no hooks and writes no snapshot.

### NAS over SMB (Dolphin / KDE network)

**Settings → Sources & destinations → NAS / network …** opens KDE's native
folder dialog directly in the SMB network. Choose your NAS, share and dedicated
backup folder. **Choose folder …** also accepts network destinations. If your
NAS does not appear in automatic discovery, enter its network address in the
dialog's location bar.

**Open** copies the selected folder into the repository field and leaves
Settings open. Only **Save** writes the configuration permanently. **Cancel** in
the folder dialog preserves the previous path.

For example, a Dolphin folder at `smb://neo@nas.local/NAS/CachyOS Backup/` is
stored as `smb://neo@nas.local/NAS/CachyOS%20Backup`. Changing local KIO mount
paths are not stored in the configuration.

```json
{
  "name": "nas",
  "display_name": "NAS",
  "repository": "smb://neo@nas.local/NAS/CachyOS%20Backup",
  "schedule": "*-*-* 03:00:00"
}
```

Requires **kio-fuse**, **kio-extras** and a running KDE user session. Open the
share in Dolphin first and save its login credentials in **KDE Wallet**, so
scheduled backups work without a password dialog. The NAS login password and
rustic's separate repository password are different credentials. NAS passwords
are not stored in the repository URL; SMB requires no backend options.

Before each rustic invocation, the application reconnects the saved URL through
the official [KIO-FUSE D-Bus service](https://github.com/KDE/kio-fuse#usage).
rustic then accesses the repository as a filesystem. The opened network folder
stays bound to that filesystem during the operation. Missing connections produce
a clear error; no local replacement repository is created. KIO mounts are
automatically excluded from backups. Without a logged-in KDE session, use a
persistent SMB/NFS mount or a direct rustic backend such as SFTP.

### NAS over SFTP

```json
{
  "name": "nas",
  "display_name": "Synology NAS",
  "repository": "opendal:sftp",
  "options": {
    "endpoint": "ssh://192.168.178.121:22",
    "user": "backupuser",
    "root": "/volume1/backup/rustic"
  },
  "schedule": "*-*-* 03:00:00"
}
```

The native SFTP backend requires working SSH key authentication. Check access
and backend support with your installed rustic version. Alternatively, mount
the NAS persistently using SMB/NFS and use its local mount path as the repository,
or configure `rclone:REMOTE:path`. Dolphin SMB URLs use KIO FUSE as described
above. restic URLs such as `sftp:user@host:/path` are rejected with an explanation
because rustic uses a different backend configuration.

### S3

```json
{
  "name": "offsite",
  "repository": "opendal:s3",
  "options": {
    "bucket": "my-backup-bucket",
    "region": "eu-central-1",
    "root": "cachyos"
  },
  "env_file": "~/.config/cachyos-time-machine/offsite-env.json",
  "schedule": "*-*-* 04:00:00"
}
```

`offsite-env.json` (set private 0600 permissions):

```json
{
  "AWS_ACCESS_KEY_ID": "YOUR-ACCESS-KEY",
  "AWS_SECRET_ACCESS_KEY": "YOUR-SECRET-KEY"
}
```

Credential files and alternative password files are automatically excluded from
backups. Backend options follow rustic/OpenDAL. See more
[rustic configuration examples](https://github.com/rustic-rs/rustic/tree/main/config/services).

### Exclusions

In **Retention & exclusions**, **Exclude files …** and **Exclude folders …** open
the file explorer. Selected paths are converted to exclusion patterns, including
subfolders. Special characters in names are escaped; custom patterns are preserved.

`excludes.txt` uses **rustic globs**: `!` means **exclude**, while positive
patterns mean **include**. Positive patterns can implicitly exclude all other
files, so remember the `!` when excluding files.

```text
# Native rustic globs
!.cache/
!.local/share/Trash/
!Downloads/
!*.iso
```

The application appends protective patterns for repository directories, local
passwords, environment files, state/logs, `~/Restored` and the rustic cache last.
This keeps them out of backups and prevents recursively backing up the backup
repository itself.

### Scheduling and retention

Since version 0.2.3, each destination's schedule uses a **Frequency** selector:
manual only, hourly, daily, weekly, monthly or yearly. Relevant controls for
time, minute, weekday, month and day appear automatically. Times use the local
time zone. Runs are skipped on nonexistent dates, such as April 31, with an
explanation in the dialog. Existing special systemd schedules appear under
**Custom** and are preserved when saving other settings.

Changes to `config.json` automatically appear in the popup. Then choose
**Enable schedules** or run `cachyos-time-machine install`. The application
remembers the activation state it last set; for timers changed outside the
application, `systemctl --user list-timers` is authoritative.

`Persistent=true` catches up missed runs when the user service manager starts
again. It does not wake the PC from sleep or guarantee execution while powered
off. To run without a logged-in session, you can use
`loginctl enable-linger "$USER"`; external drives, SSH agents and secrets must
also be available without a desktop session.

Retention only runs after a fully successful backup and filters by the
`cachyos-time-machine` snapshot label. Snapshots with other labels are not
deleted by this rule. rustic removes unused data using its own prune rules, so
storage usage may not decrease immediately. Cleanup errors are shown separately
without treating a successfully saved snapshot as a lost backup. rustic warnings
are conservatively treated as an incomplete backup; retention is then skipped.

## Restoring files

**Restore files** opens the browser inside the same popup. Choose a date,
double-click a folder, select a file and click **Restore selection**. **This
folder** restores the current folder. The path field, Up button and text filter
help with navigation. Changing dates preserves the path. A running restore can
be cancelled using **Back → Cancel**.

Every restore creates a new private directory, for example:
`~/Restored/2026-10-09_18-30-00_ab12cd34/home/eugen/Documents/file.txt`.
CLI `--target` also creates a new subfolder within the chosen destination. When
restoring a file, the notification action opens its parent folder. You can then
move restored files back yourself.

## Terminal

If `~/.local/bin` is not on your PATH, use the full launcher path.

```bash
cachyos-time-machine gui
cachyos-time-machine autostart enable
cachyos-time-machine autostart disable
cachyos-time-machine autostart status
cachyos-time-machine configure
cachyos-time-machine key set --dest usb
cachyos-time-machine init --dest usb
cachyos-time-machine install
cachyos-time-machine backup --dest usb
cachyos-time-machine backup --dest usb --dry-run
cachyos-time-machine check --dest usb
cachyos-time-machine snapshots --dest usb --json
cachyos-time-machine ls --dest usb --snapshot SNAPSHOT_ID --path /home/eugen --json
cachyos-time-machine restore --dest usb --snapshot SNAPSHOT_ID --path /home/eugen/Documents
cachyos-time-machine cancel --dest usb
cachyos-time-machine destinations --json
cachyos-time-machine stats --dest usb
cachyos-time-machine log --dest usb
cachyos-time-machine pause
cachyos-time-machine key show --dest usb
cachyos-time-machine key save-1password --dest usb
cachyos-time-machine key save-1password --dest usb --vault Private
systemctl --user list-timers 'cachyos-time-machine-*'
```

Repository commands return JSON and exit status 0/1. `key show`, `configure`, and
`log` without `--json` return plain text. Global `--config-dir` and `--state-dir`
options go before the subcommand.

## Development and tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . pytest ruff
python -m ruff check timemachine tests install.py
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Set `RUSTIC_TEST_BINARY=/path/to/rustic` to choose a separate test binary.
Without rustic, only integration tests are skipped. GitHub Actions installs
rustic 0.11.4 with a pinned SHA256 and performs real backup/restore tests. All
test repositories are temporary; personal files and backups are not used.

Coverage includes local repository initialization, incremental backups, snapshot
history, folder/file restore, Unicode filenames, exclusions, dry runs, checks,
wrong passwords, cancellation, concurrent access and Qt browser workers. The
D-Bus backup/browser/restore interface, autostart and Plasma QML syntax are also
tested. The Arch Linux CI job loads the real applet in the system tray of a full
Plasma 6 shell on a virtual X11 display. Actual Qt mouse events check applet
selection, popup visibility, closing on a second click, keyboard activation and
the production SVG icon.

Native file dialogs are tested on X11 and a separate headless Wayland compositor
with local files and a real Samba test share. The user's actual CachyOS/KDE
Wayland session, physical NAS/cloud devices and 1Password are not available for
integration tests. Version 0.2.1 added immediate startup, system tray migration
and bundled icons. Tests explicitly require applet, popup, D-Bus and SVG readiness;
a test viewer merely remaining alive does not count as success.

The previous Qt main window remains available through
`cachyos-time-machine gui --window`; it is not the default interface. Its Qt
restore browser keyboard shortcuts remain available there.

## File selection and crash diagnostics

Since version 0.2.6, native KDE file dialogs for sources, exclusions and
repositories run in separate `kdialog` processes. They support local folders and,
for repositories, SMB shares. **Open** transfers the selection to Settings;
only **Save** writes the configuration. Cancelling or a file dialog crash keeps
your input and does not terminate the service. Missing `kdialog` produces an
installation hint.

The background service records its version, Qt/PySide versions, Python errors
and native crash reports in
`~/.local/state/cachyos-time-machine/desktop-service.log`, including when started
through D-Bus. Only your user can read this log. Check it if another problem
occurs. After an application update, log out and back in to restart the existing
service; its startup log entry should show the new version.

## Updating and uninstalling

For a user-local installation, run `git pull`, `python install.py`, then
`~/.local/bin/cachyos-time-machine install` to rewrite timers. After an applet
update, log out of KDE and back in so Plasma and the service load the new
version. This also applies to updated settings dialogs: running Python processes
keep their loaded modules.

Before upgrading from 0.1.x, choose **Quit** in the old tray menu and finish any
running operations. After updating, click the new panel icon or run
`cachyos-time-machine gui`. Loaded Plasma applets pick up QML updates when removed
and added again, or at the next KDE login.

`python install.py --no-panel` installs without changing the running panel.

```bash
python install.py --uninstall
```

The application and its timers are removed. Configuration, passwords, logs and
backup repositories are retained. The system tray entry, separate panel applet
and application autostart entry are removed.

MIT. Attribution and technical porting details: [docs/UPSTREAM.md](docs/UPSTREAM.md).
