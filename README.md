# CachyOS Time Machine · rustic

Dateiversionen für CachyOS KDE, inspiriert von
[Omarchy Time Machine](https://github.com/jankeesvw/omarchy-time-machine).
Die gesamte Backup-Verarbeitung übernimmt **[rustic](https://github.com/rustic-rs/rustic)**.
Die Standardoberfläche ist ein **natives Plasma-6-Miniprogramm**: Ein Klick auf
das Leisten-Symbol öffnet ein **an der KDE-Leiste verankertes Popup**. Status,
Backups und der Snapshot-Dateibrowser erscheinen dort, ohne separates Hauptfenster.
Plasma übernimmt Positionierung, Theme und Popup-Verhalten auch unter Wayland.
Ein Python/PySide6-Dienst verbindet das Miniprogramm über den Sitzungs-D-Bus mit
der rustic-CLI. Einstellungs-, Schlüssel- und Protokolldialoge bleiben Qt-Dialoge.

## Funktionen

- Ein ruhiges Leisten-Symbol; rot bei Fehlern oder überfälligem Backup,
  blau während eines Vorgangs, orange vor der Einrichtung. Der Status erscheint als farbiger Punkt am Symbol.
- Mehrere Ziele mit eigenen Zeitplänen, Schlüsseln, Status und Protokollen.
- Automatische Sicherungen mit persistenten systemd-Benutzertimern und
  manuelle Backups aus dem Plasma-Popup oder Terminal.
- Schaltbarer Autostart bei der KDE-Anmeldung, im Popup und in den Einstellungen.
  KDE startet den Dienst bei Bedarf über D-Bus, auch wenn der Autostart aus ist.
- Verschlüsselte, deduplizierte und inkrementelle Backups; jede Sicherung
  ist ein vollständig wiederherstellbarer Dateistand.
- Lokale/externe Laufwerke, NAS, SFTP, S3, REST, rclone und weitere rustic-Backends.
- Eine oder mehrere Quellen, Ausschlussmuster und konfigurierbare Aufbewahrung.
- Fortschritt, Abbruch, Integritätsprüfung, Testlauf und Offline-Statusanzeige.
- Snapshot-Browser mit Datumsauswahl, Verzeichnisnavigation und Textfilter.
  Beim Wechsel des Datums bleibt der aktuelle Pfad erhalten.
- Einzelne Dateien oder ganze Ordner in neue Verzeichnisse unter `~/Restored`
  zurückholen; aktuelle Dateien werden dabei nicht überschrieben.
- Desktop-Benachrichtigungen und Öffnen der Wiederherstellung in Dolphin.
- Passwortdatei oder externer Passwortbefehl; optionaler 1Password-Export.
- Vorbereitungs- und Fehler-Hooks, Protokollaufbewahrung für 30 Tage.

## Installation auf CachyOS KDE

Benötigt KDE **Plasma >= 6.3**, Kirigami, Python >= 3.11, Qt/PySide6 >= 6.6
und **rustic >= 0.11.4**.
rustic und PySide6 sind in den Arch-/CachyOS-Paketquellen verfügbar.
Der pacman-Paketname lautet **`pyside6`**; das Python-Modul heißt `PySide6`.

```bash
sudo pacman -Syu pyside6 rustic libnotify git plasma-workspace kirigami &&
git clone https://github.com/xNeo92x/cachyos-timemachine-rustic.git &&
cd cachyos-timemachine-rustic &&
python install.py &&
~/.local/bin/cachyos-time-machine gui
```

Der Installer installiert für deinen Benutzer und benötigt selbst kein sudo.
Er legt das Plasma-Miniprogramm, einen Menüeintrag, die D-Bus-Aktivierung und
einen KDE-Autostart-Eintrag an. In einer laufenden KDE-Sitzung fügt er das Symbol
einmal zur vorhandenen Leiste hinzu. Deine übrige Leistenkonfiguration bleibt erhalten.
Falls KDE die automatische Ergänzung nicht erlaubt: **Leiste bearbeiten →
Miniprogramme hinzufügen → CachyOS Time Machine**. Bei erstmals installierten
Miniprogrammen kann KDE eine erneute Anmeldung benötigen.

**Ein Klick auf das Symbol öffnet das Popup.** Es enthält Zielauswahl, Backup,
Prüfung, Testlauf, Abbruch, Wiederherstellung und Zeitplanung. Der Schalter
**Autostart bei KDE-Anmeldung** steuert den Hintergrunddienst. Ausschalten
entfernt weder das Miniprogramm noch die unabhängigen systemd-Backup-Zeitpläne;
der Dienst startet beim nächsten Zugriff des Miniprogramms bei Bedarf.
Der Installer erhält den zuletzt gewählten Autostart-Zustand bei Updates.

Alternativ kann das Miniprogramm im **Systemabschnitt → Einträge** aktiviert
werden. Dann das zusätzlich in der Leiste platzierte Symbol entfernen, um nur
einen Eintrag zu haben. Der alte Qt-Tray-Eintrag wird im Standardmodus nicht mehr erzeugt.

Optional als Arch-Paket statt Benutzerinstallation:

```bash
cd packaging
makepkg -si
```

Bei Paketinstallation das Miniprogramm hinzufügen oder `cachyos-time-machine gui`
ausführen; Autostart im Popup einschalten.
Das PKGBUILD ist im Repository enthalten; eine Veröffentlichung im AUR ist damit
nicht verbunden.

## Erste Sicherung

1. Im Popup **Einstellungen** öffnen. Quellen und ein oder mehrere Ziele
   festlegen. Der Starterpfad `CHANGE-ME` muss ersetzt werden.
2. **Schlüssel → Schlüssel speichern**. Passwort zusätzlich außerhalb des PCs
   sichern, beispielsweise in einem Passwortmanager.
3. Im Popup **Initialisieren**, dann **Jetzt sichern**.
4. **Zeitpläne aktivieren**. Speichern der Einstellungen schreibt und aktiviert
   ebenfalls die Zeitpläne neu. Fehler dabei werden angezeigt.

Der Schlüssel liegt standardmäßig unter
`~/.config/cachyos-time-machine/keys/NAME.password` mit Dateirechten **0600**.
Er gelangt weder in die Prozessargumente noch in die Protokolle und wird vom
Backup ausgeschlossen. Die lokale Passwortdatei ist nicht zusätzlich durch
KWallet verschlüsselt; sie entspricht dem unbeaufsichtigten Datei-Modell des
Originals. Mit `password_command` kann ein externer Schlüsselspeicher verwendet
werden, sofern er auch im systemd-Benutzerkontext ohne Eingabe erreichbar ist.

## Konfiguration

`~/.config/cachyos-time-machine/config.json`:

```json
{
  "source": ["~"],
  "exclude_file": "excludes.txt",
  "stale_hours": 48,
  "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 3},
  "destinations": [
    {
      "name": "usb",
      "display_name": "Mein Backup-Laufwerk",
      "repository": "/run/media/DEIN-BENUTZER/Backup/rustic",
      "schedule": "*-*-* 03:00:00"
    }
  ]
}
```

`source` kann auch eine einzelne Zeichenkette sein. Jede Quelle muss vorhanden
sein, sonst schlägt die Sicherung insgesamt fehl. Es wird als normaler Benutzer
gesichert; z. B. ein Backup von `/etc` umfasst nur lesbare Dateien. Dies ist ein
Dateibackup mit Versionshistorie, kein bootfähiges Systemabbild.

| Option | Bedeutung |
| --- | --- |
| `name` | Eindeutiger Zielname: Buchstaben/Ziffern, `-` oder `_` |
| `display_name` | Anzeigename, standardmäßig `name` |
| `repository` | Lokaler Pfad oder native rustic-Backendangabe |
| `schedule` | systemd-OnCalendar; leer/fehlend bedeutet nur manuell |
| `retention` | Globale oder zielbezogene Aufbewahrung; mindestens ein positiver Wert |
| `stale_hours` | Warnschwelle seit letzter erfolgreicher Sicherung, global oder je Ziel |
| `pre_command` | Ziel vorbereiten, z. B. Mount-Service starten; auch vor Browser/Prüfung/Init |
| `on_failure_command` | Bei fehlgeschlagenem Backup ausführen |
| `hook_timeout` | Hook-Zeitlimit in Sekunden, standardmäßig 120 |
| `password_file` | Alternative Passwortdatei, muss Rechte 0600 besitzen |
| `password_command` | Alternativer rustic-Passwortbefehl; nicht zusammen mit `password_file` |
| `options` | String-Werte für rustic `[repository.options]` |
| `env_file` | Pfad einer JSON-Datei mit Umgebungsvariablen für dieses Ziel |
| `env` | Direkt definierte Umgebungsvariablen für dieses Ziel |

Eigene Hook-Befehle werden ausdrücklich über `/bin/sh -c` als dein Benutzer
ausgeführt. Ein Testlauf führt keine Hooks aus und schreibt keinen Snapshot.

### NAS über SFTP

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

Der native SFTP-Backend benötigt funktionierende SSH-Schlüsselauthentifizierung;
Zugang und Backend-Unterstützung mit der installierten rustic-Version prüfen.
Alternativ ein NAS per SMB/NFS als echtes Dateisystem einhängen und den lokalen
Mount-Pfad als Repository nutzen, oder `rclone:REMOTE:pfad` konfigurieren.
Eine `smb://`-Adresse aus Dolphin ist kein lokal eingehängter Verzeichnispfad.
restic-URLs wie `sftp:user@host:/pfad` werden bewusst mit einer Erklärung
abgelehnt; rustic verwendet eine andere Backend-Konfiguration.

### S3

```json
{
  "name": "offsite",
  "repository": "opendal:s3",
  "options": {
    "bucket": "mein-backup-bucket",
    "region": "eu-central-1",
    "root": "cachyos"
  },
  "env_file": "~/.config/cachyos-time-machine/offsite-env.json",
  "schedule": "*-*-* 04:00:00"
}
```

`offsite-env.json` (private Rechte 0600 setzen):

```json
{
  "AWS_ACCESS_KEY_ID": "DEIN-ZUGANGSSCHLUESSEL",
  "AWS_SECRET_ACCESS_KEY": "DEIN-GEHEIMER-SCHLUESSEL"
}
```

Zugangsdaten-Dateien und alternative Passwortdateien werden automatisch vom
Backup ausgeschlossen. Backend-Optionen richten sich nach rustic/OpenDAL;
mehr Beispiele: [rustic-Konfigurationen](https://github.com/rustic-rs/rustic/tree/main/config/services).

### Ausschlüsse

`excludes.txt` verwendet **rustic-Globs**. Wichtig: `!` bedeutet hier **ausschließen**,
positive Muster bedeuten **einschließen**. Positive Muster können alle anderen
Dateien implizit ausschließen; beim Ausschließen daher das `!` nicht vergessen.

```text
# Native rustic-Globs
!.cache/
!.local/share/Trash/
!Downloads/
!*.iso
```

Die App hängt Schutzmuster für Repository-Verzeichnisse, lokale Schlüssel,
Umgebungsdateien, Status/Protokolle, `~/Restored` und den rustic-Cache zuletzt an.
Sie sollen weder in die Sicherung geraten noch ein rekursives Backup des
Backup-Repositorys erzeugen.

### Zeitplanung und Aufbewahrung

Änderungen an `config.json` erscheinen automatisch im Popup. Danach
**Zeitpläne aktivieren** wählen oder `cachyos-time-machine install` ausführen.
Die App merkt den zuletzt selbst gesetzten Aktivierungszustand; für außerhalb
der App geänderte Timer ist `systemctl --user list-timers` maßgeblich.

`Persistent=true` holt verpasste Termine nach, sobald der Benutzer-Service-Manager
wieder läuft. Es weckt den PC nicht aus dem Standby und garantiert keine
Ausführung bei ausgeschaltetem Gerät. Für Betrieb ohne angemeldete Sitzung kann
bei Bedarf `loginctl enable-linger "$USER"` verwendet werden; externe Laufwerke,
SSH-Agent und Secrets müssen dann ebenfalls ohne Desktop-Sitzung verfügbar sein.

Aufbewahrung läuft nur nach einem vollständig erfolgreichen Backup und filtert
nach dem App-Snapshotlabel `cachyos-time-machine`. Andere Snapshotlabels werden
nicht durch diese Regel gelöscht. rustic entfernt ungenutzte Daten mit seinen
eigenen Prune-Regeln; dadurch muss der Speicher nicht sofort sinken.
Bereinigungsfehler werden getrennt angezeigt, ohne den erfolgreichen Datenstand
als verlorenes Backup zu behandeln. Warnungen von rustic zählen vorsorglich als
unvollständiger Backup-Lauf; dann wird keine Aufbewahrung ausgeführt.

## Wiederherstellung

**Dateien wiederherstellen** öffnet den Browser im selben Popup. Datum auswählen,
Ordner per Doppelklick öffnen, Datei auswählen und **Auswahl wiederherstellen**
anklicken. **Diesen Ordner** stellt das aktuelle Verzeichnis wieder her.
Pfadfeld, Nach-oben-Schaltfläche und Textfilter helfen beim Navigieren.
Beim Datumswechsel bleibt der Pfad erhalten. Eine laufende Wiederherstellung
lässt sich über **Zurück → Abbrechen** stoppen.

Jeder Restore erzeugt einen eigenen privaten Ordner, beispielsweise:
`~/Restored/2026-10-09_18-30-00_ab12cd34/home/eugen/Dokumente/datei.txt`.
Auch mit CLI-`--target` wird darunter ein neuer Unterordner angelegt.
Beim Wiederherstellen einer Datei öffnet die Benachrichtigungsaktion den
zugehörigen Ordner. Die Dateien kannst du anschließend selbst zurück verschieben.

## Terminal

Falls `~/.local/bin` noch nicht im PATH ist, die vollständige Programmadresse nutzen.

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
cachyos-time-machine restore --dest usb --snapshot SNAPSHOT_ID --path /home/eugen/Dokumente
cachyos-time-machine cancel --dest usb
cachyos-time-machine destinations --json
cachyos-time-machine stats --dest usb
cachyos-time-machine log --dest usb
cachyos-time-machine pause
cachyos-time-machine key show --dest usb
cachyos-time-machine key save-1password --dest usb
cachyos-time-machine key save-1password --dest usb --vault Privat
systemctl --user list-timers 'cachyos-time-machine-*'
```

Repositorybefehle liefern JSON und Exitcode 0/1. `key show`, `configure` und
`log` ohne `--json` liefern Klartext. Globale Optionen `--config-dir` und
`--state-dir` stehen vor dem Unterbefehl.

## Entwicklung und Tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . pytest ruff
python -m ruff check timemachine tests install.py
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

`RUSTIC_TEST_BINARY=/pfad/zu/rustic` wählt ein separates Testbinary.
Ohne rustic werden nur die Integrationstests übersprungen.
Die GitHub-Actions-Konfiguration installiert rustic 0.11.4 mit festem SHA256 und
führt ebenfalls echte Backup-/Restore-Tests aus. Testrepositories sind temporär;
deine persönlichen Daten und Backups werden nicht verwendet.

Getestet: echte lokale Repository-Initialisierung, inkrementelle Sicherung,
Snapshot-Historie, Ordner-/Datei-Restore, Unicode-Dateinamen, Ausschlüsse, Testlauf,
Prüfung, falsches Passwort, Abbruch, konkurrierende Zugriffe und Qt-Browserprozesse.
Zusätzlich werden die D-Bus-Schnittstelle inklusive Backup/Browser/Restore und
Autostart sowie die Plasma-QML-Syntax geprüft. Der separate Arch-Linux-CI-Job
lädt das echte Miniprogramm mit Plasma 6 und öffnet dessen Popup im Offscreen-Modus.
Eine vollständige CachyOS-/KDE-Wayland-Sitzung, echte NAS-/Cloud-Ziele und
1Password stehen hier nicht für Integrationstests zur Verfügung. Version 0.2.0
ergänzt die native Plasma-Integration.

Das bisherige Qt-Hauptfenster bleibt bei Bedarf mit
`cachyos-time-machine gui --window` zugänglich. Es ist nicht der Standardmodus.
Die Tastaturkürzel des bisherigen Qt-Restore-Browsers gelten dort weiterhin.

## Aktualisieren und Entfernen

Für Benutzerinstallation: `git pull`, `python install.py`, anschließend
`~/.local/bin/cachyos-time-machine install`, um Timer neu zu schreiben.
Vor dem Wechsel von 0.1.x die alte Anwendung im bisherigen Tray-Menü über
**Beenden** schließen und laufende Vorgänge abschließen. Nach dem Update das neue
Leisten-Symbol anklicken oder `cachyos-time-machine gui` starten. Bereits geladene
Plasma-Miniprogramme übernehmen QML-Updates nach Entfernen/erneutem Hinzufügen
oder bei der nächsten KDE-Anmeldung.

`python install.py --no-panel` installiert ohne Änderung der laufenden Leiste.

```bash
python install.py --uninstall
```

Die Anwendung und ihre Timer werden entfernt. Konfiguration, Schlüssel,
Protokolle und die Backup-Repositories bleiben erhalten. Das automatisch hinzugefügte
Leisten-Miniprogramm und der eigene Autostart-Eintrag werden entfernt. Manuell im
Systemabschnitt aktivierte Einträge gegebenenfalls dort wieder deaktivieren.

MIT. Herkunft und technische Portierungsdetails: [docs/UPSTREAM.md](docs/UPSTREAM.md).
