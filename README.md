# CachyOS Time Machine · rustic

**Deutsch** | [English](README.en.md)

Dateiversionen für CachyOS KDE, inspiriert von
[Omarchy Time Machine](https://github.com/jankeesvw/omarchy-time-machine).
Die gesamte Backup-Verarbeitung übernimmt **[rustic](https://github.com/rustic-rs/rustic)**.
Die Standardoberfläche ist ein **natives Plasma-6-Miniprogramm**: Ein Klick auf
das Leisten-Symbol öffnet ein **an der KDE-Leiste verankertes Popup**. Status,
Backups und der Snapshot-Dateibrowser erscheinen dort, ohne separates Hauptfenster.
Plasma übernimmt Positionierung, Theme und Popup-Verhalten auch unter Wayland.
Ein Python/PySide6-Dienst verbindet das Miniprogramm über den Sitzungs-D-Bus mit
der rustic-CLI. Einstellungs-, Schlüssel- und Protokolldialoge bleiben Qt-Dialoge.

## Hinweis zur Entstehung und Weiterentwicklung

Dieses komplette Projekt wurde mit **ChatGPT** erstellt. Vorzugsweise sollte
jemand das Projekt **forken**, den Code prüfen und optimieren sowie die weitere
Entwicklung und Pflege übernehmen. Forks zur Verbesserung und langfristigen
Weiterführung des Projekts sind ausdrücklich erwünscht.

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
- NAS-Ordner über den KDE-Netzwerkdialog auswählen; SMB-Adressen werden vor
  jedem Zugriff automatisch über KIO FUSE verbunden, auch bei geplanten Backups.
- Eine oder mehrere Quellen, Ausschlussmuster und konfigurierbare Aufbewahrung.
- Fortschritt, Abbruch, Integritätsprüfung, Testlauf und Offline-Statusanzeige.
- Snapshot-Browser mit Datumsauswahl, Verzeichnisnavigation und Textfilter.
  Beim Wechsel des Datums bleibt der aktuelle Pfad erhalten.
- Einzelne Dateien oder ganze Ordner in neue Verzeichnisse unter `~/Restored`
  zurückholen; aktuelle Dateien werden dabei nicht überschrieben.
- Desktop-Benachrichtigungen und Öffnen der Wiederherstellung in Dolphin.
- Passwortdatei oder externer Passwortbefehl; optionaler 1Password-Export.
- Vorbereitungs- und Fehler-Hooks, Protokollaufbewahrung für 30 Tage.
- Deutsche und englische Oberfläche; Systemsprache als Standard, jederzeit in den Einstellungen änderbar.

## Sprache der Oberfläche

Unter **Einstellungen → Quellen & Ziele → Sprache** stehen **Systemsprache verwenden**,
**Deutsch** und **English** zur Auswahl. Die Systemsprache ist voreingestellt:
Deutsch bei deutscher Systemsprache, Englisch bei englischer oder einer anderen
Systemsprache. KDE-Sprachpräferenzen (`LANGUAGE`) und die Locale-Einstellungen
werden berücksichtigt.

**Speichern** übernimmt die Sprache sofort in das Plasma-Popup und die Qt-Dialoge;
eine erneute Anmeldung ist für den Sprachwechsel nicht nötig. Die Auswahl bleibt
über Neustarts erhalten. Eigene Zielnamen, Pfade, Ausschlussmuster und Zeitpläne
werden nicht übersetzt oder verändert. Bereits vorhandene Protokolle und von
rustic selbst ausgegebene Meldungen bleiben in ihrer ursprünglichen Sprache.

## Installation auf CachyOS KDE

Benötigt KDE **Plasma >= 6.3**, Kirigami, Python >= 3.11, Qt/PySide6 >= 6.6
und **rustic >= 0.11.4**.
rustic und PySide6 sind in den Arch-/CachyOS-Paketquellen verfügbar.
Der pacman-Paketname lautet **`pyside6`**; das Python-Modul heißt `PySide6`.

```bash
sudo pacman -Syu pyside6 rustic libnotify git plasma-workspace kirigami kio-fuse kio-extras kdialog &&
git clone https://github.com/xNeo92x/cachyos-timemachine-rustic.git &&
cd cachyos-timemachine-rustic &&
python install.py &&
~/.local/bin/cachyos-time-machine gui
```

Der Installer installiert für deinen Benutzer und benötigt selbst kein sudo.
Er legt das Plasma-Miniprogramm, einen Menüeintrag, die D-Bus-Aktivierung und
einen KDE-Autostart-Eintrag an. In einer laufenden KDE-Sitzung aktiviert er das Symbol im vorhandenen
**Systemabschnitt**, neben den anderen Statussymbolen und vor der Uhr.
Ein separat am rechten Leistenende platziertes Symbol aus Version 0.2.0 wird
automatisch entfernt. Deine übrige Leistenkonfiguration bleibt erhalten.
Falls KDE die automatische Ergänzung nicht erlaubt: **Systemabschnitt einrichten →
Einträge → CachyOS Time Machine → Immer angezeigt**.
Das SVG wird direkt als Bild aus dem Miniprogramm geladen; der Icon-Theme-Cache
wird dafür nicht verwendet. Nach einem Widget-Update bitte einmal bei KDE ab-
und wieder anmelden: Plasma hält bereits geladene QML-Komponenten im Speicher.

**Ein Klick auf das Symbol öffnet das Popup.** Es enthält Zielauswahl, Backup,
Prüfung, Testlauf, Abbruch, Wiederherstellung und Zeitplanung. Der Schalter
**Autostart bei KDE-Anmeldung** steuert den Hintergrunddienst. Ausschalten
entfernt weder das Miniprogramm noch die unabhängigen systemd-Backup-Zeitpläne;
der Dienst startet beim nächsten Zugriff des Miniprogramms bei Bedarf.
Der Installer erhält den zuletzt gewählten Autostart-Zustand bei Updates.

Alternativ lässt sich das Miniprogramm als einzelnes Leisten-Widget hinzufügen.
Der Installer und der Menüeintrag verwenden standardmäßig den Systemabschnitt.
Der alte Qt-Tray-Eintrag wird im Standardmodus nicht mehr erzeugt.

### Sofortiger Start nach Installation

Version 0.2.1 aktualisiert die D-Bus-Aktivierung der laufenden Sitzung. Falls
der Sitzungsbus die neue Service-Datei trotzdem noch nicht erkennt, startet
`cachyos-time-machine gui` den Dienst direkt und wartet auf dessen Bereitschaft.
Eine erneute KDE-Anmeldung ist dafür nicht erforderlich. Bei einem tatsächlichen
Startfehler enthält `~/.local/state/cachyos-time-machine/desktop-service.log`
die Details (bei eigenen XDG-Pfaden entsprechend im Statusordner).

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
   festlegen. Quellen lassen sich über **Dateien auswählen …** (Mehrfachauswahl)
   und **Ordner auswählen …** hinzufügen. Beim Repository wählt **Ordner
   auswählen …** ein lokales Ziel oder einen bereits eingehängten NAS-/USB-Ordner.
   Im Dateidialog kann auch ein eigener Backup-Ordner angelegt werden. Der
   Starterpfad `CHANGE-ME` muss ersetzt werden; Remote-Backends behalten ihr
   Repository-Feld und die Backend-Optionen.
2. Optional: Im Popup **Passwort …** öffnen und ein eigenes Passwort speichern.
   Zusätzlich außerhalb des PCs sichern, beispielsweise in einem Passwortmanager.
   Ohne eigenes Passwort diesen Schritt überspringen.
3. **Jetzt sichern**. Ein neues Repository wird beim ersten Backup automatisch
   initialisiert; das gilt auch für einen automatisch gestarteten Zeitplan.
   **Initialisieren** ist nur noch eine zusätzliche manuelle Möglichkeit.
4. **Zeitpläne aktivieren**. Speichern der Einstellungen schreibt und aktiviert
   ebenfalls die Zeitpläne neu. Fehler dabei werden angezeigt.

Ohne gespeichertes Passwort verwendet die Anwendung das von rustic unterstützte
leere Passwort. Es gibt keine Passwortabfrage und keine erforderliche Schlüsseldatei.
Das rustic-Repositoryformat bleibt verschlüsselt, bietet mit einem leeren Passwort
aber keinen Passwortschutz: Personen mit Zugriff auf das Repository können die
Sicherungen lesen. Ein bestehendes Repository mit eigenem Passwort benötigt weiterhin
sein ursprüngliches Passwort; es wird weder neu angelegt noch auf ein leeres Passwort
umgestellt. Eine ausdrücklich konfigurierte, fehlende `password_file` bleibt ein Fehler.

Für ein von der Anwendung bereits ohne Passwort verwendetes Repository setzt
**Passwort …** nachträglich ein eigenes Passwort und ersetzt dabei den leeren
Zugang. Die bestehenden Snapshots bleiben erhalten. Bereits gespeicherte eigene
Passwörter werden nicht überschrieben. Ein Fehler während einer Passwortänderung
lässt die neue lokale Datei mit Endung `.pending` zur Wiederherstellung bestehen.

Ein optional gespeicherter Schlüssel liegt standardmäßig unter
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
  "language": "system",
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
| `language` | Globale Oberflächensprache: `system` (Standard), `de` oder `en` |
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

### NAS über SMB (Dolphin / KDE Netzwerk)

In **Einstellungen → Quellen & Ziele → NAS / Netzwerk …** öffnet sich der
native KDE-Ordnerdialog direkt im SMB-Netzwerk. Wähle deine NAS, die Freigabe
und einen eigenen Backup-Ordner. Auch **Ordner auswählen …** erlaubt jetzt
Netzwerkziele. Die Netzwerkadresse lässt sich bei Bedarf oben im Dialog öffnen,
wenn die NAS in der automatischen Netzwerksuche nicht auftaucht.

**Öffnen** übernimmt den Ordner in das Repository-Feld und lässt die
Einstellungen geöffnet. Erst **Speichern** übernimmt die Konfiguration
dauerhaft. **Abbrechen** im Ordnerdialog erhält den bisherigen Pfad.

Beispiel: Der in Dolphin sichtbare Ordner
`smb://neo@nas.local/NAS/CachyOS Backup/` wird dauerhaft als
`smb://neo@nas.local/NAS/CachyOS%20Backup` gespeichert. Ein wechselnder lokaler
KIO-Mount-Pfad wird nicht in der Konfiguration gespeichert.

```json
{
  "name": "nas",
  "display_name": "NAS",
  "repository": "smb://neo@nas.local/NAS/CachyOS%20Backup",
  "schedule": "*-*-* 03:00:00"
}
```

Benötigt **kio-fuse** und **kio-extras** sowie eine laufende KDE-Benutzersitzung.
Öffne die Freigabe zunächst in Dolphin und speichere die NAS-Anmeldedaten in
**KDE Wallet**, damit geplante Sicherungen ohne Passwortdialog funktionieren.
Das NAS-Anmeldepasswort und der separate Verschlüsselungsschlüssel für rustic
sind unterschiedliche Zugangsdaten. NAS-Passwörter werden nicht in der
Repository-Adresse gespeichert; SMB benötigt keine Backend-Optionen.

Vor jedem rustic-Aufruf verbindet die Anwendung die gespeicherte Adresse neu
über den offiziellen [KIO-FUSE-D-Bus-Dienst](https://github.com/KDE/kio-fuse#usage).
rustic verarbeitet das Repository anschließend als Dateisystem. Der geöffnete
Netzwerkordner bleibt während des Aufrufs an dieses Dateisystem gebunden.
Bei fehlender Verbindung wird mit einer verständlichen Meldung abgebrochen;
ein lokales Ersatz-Repository wird nicht angelegt. KIO-Mounts sind automatisch
vom Backup ausgeschlossen. Ohne angemeldete KDE-Sitzung bitte einen dauerhaften
SMB-/NFS-Mount oder einen direkten rustic-Backend wie SFTP verwenden.

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
Alternativ ein NAS per SMB/NFS dauerhaft einhängen und den lokalen Mount-Pfad
als Repository nutzen, oder `rclone:REMOTE:pfad` konfigurieren. SMB-Adressen aus
Dolphin werden wie oben beschrieben über KIO FUSE eingebunden.
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

Unter **Aufbewahrung & Ausschlüsse** öffnen **Dateien ausschließen …** und
**Ordner ausschließen …** den Dateiexplorer. Die ausgewählten Pfade werden
automatisch als Ausschlussmuster übernommen, einschließlich Unterordnern.
Sonderzeichen in Namen werden maskiert; eigene Muster bleiben erhalten.

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

Ab Version 0.2.3 wählst du den Zeitplan pro Backup-Ziel über die
**Häufigkeit**: nur manuell, stündlich, täglich, wöchentlich, monatlich oder
jährlich. Die passenden Regler für Uhrzeit, Minute, Wochentag, Monat und Tag
werden eingeblendet. Uhrzeiten gelten in der lokalen Zeitzone. An nicht
vorhandenen Monatstagen (z. B. 31. April) entfällt der Lauf; darauf weist der
Dialog hin. Besondere vorhandene systemd-Zeitpläne erscheinen unter
**Benutzerdefiniert** und bleiben beim Speichern anderer Einstellungen erhalten.

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
lädt das echte Miniprogramm im KDE-Systemabschnitt einer vollständigen Plasma-6-Shell
auf einem virtuellen X11-Display. Er sendet echte Qt-Mausereignisse und prüft die
Auswahl des Widgets, das sichtbare Popup, Schließen durch zweiten Klick und
Tastaturaktivierung sowie das tatsächlich verwendete SVG-Bild.
Native Dateidialoge werden unter X11 und einem separaten Headless-Wayland-Compositor
mit lokalen Dateien und einer echten Samba-Testfreigabe geprüft. Die konkrete
CachyOS-/KDE-Wayland-Sitzung des Benutzers, reale NAS-/Cloud-Geräte und 1Password
stehen hier nicht für Integrationstests zur Verfügung. Version 0.2.1
ergänzt zuverlässigen Sofortstart, Systemabschnitt-Migration und gebündelte Icons.
Der native Test prüft explizit die Bereitschaft von Miniprogramm, Popup, D-Bus
und SVG; ein bloß weiterlaufender Test-Viewer gilt nicht als erfolgreicher Start.

Das bisherige Qt-Hauptfenster bleibt bei Bedarf mit
`cachyos-time-machine gui --window` zugänglich. Es ist nicht der Standardmodus.
Die Tastaturkürzel des bisherigen Qt-Restore-Browsers gelten dort weiterhin.

## Dateiauswahl und Absturzdiagnose

Ab Version 0.2.6 laufen die nativen KDE-Dateidialoge für Quellen, Ausschlüsse und
Repositories in eigenen `kdialog`-Prozessen. Sie können lokale Ordner und bei
Repositories auch SMB-Freigaben auswählen. „Öffnen“ übernimmt die Auswahl in den
Einstellungen; erst „Speichern“ schreibt die Konfiguration. Abbrechen oder ein
Absturz des Dateidialogs verändert keine Eingaben und beendet den Dienst nicht.
`kdialog` muss installiert sein; andernfalls erscheint ein Installationshinweis.

Der Hintergrunddienst schreibt seine Version, Qt-/PySide-Versionen, Python-Fehler
und native Absturzberichte auch bei D-Bus-Aktivierung nach
`~/.local/state/cachyos-time-machine/desktop-service.log` (nur für deinen Benutzer
lesbar). Falls erneut ein Problem auftritt, dieses Protokoll prüfen. Nach einem
Update muss der bereits laufende Dienst durch Ab- und Anmeldung neu starten;
der Start-Eintrag im Protokoll muss die neue Version anzeigen.

## Aktualisieren und Entfernen

Für Benutzerinstallation: `git pull`, `python install.py`, anschließend
`~/.local/bin/cachyos-time-machine install`, um Timer neu zu schreiben.
Nach einem Update des Miniprogramms einmal bei KDE ab- und wieder anmelden,
damit Plasma und der Hintergrunddienst die neue Version laden. Das gilt auch
für geänderte Einstellungsdialoge, da bereits laufende Python-Prozesse ihre
geladenen Module behalten.
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
Protokolle und die Backup-Repositories bleiben erhalten. Der Eintrag im Systemabschnitt, das separate
Leisten-Miniprogramm und der eigene Autostart-Eintrag werden entfernt.

MIT. Herkunft und technische Portierungsdetails: [docs/UPSTREAM.md](docs/UPSTREAM.md).
