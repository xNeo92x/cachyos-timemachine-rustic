# Referenzen und Portierungsentscheidungen

Die Implementierung ist neu geschrieben. Konzept und Funktionsumfang orientieren
sich an [Omarchy Time Machine](https://github.com/jankeesvw/omarchy-time-machine),
MIT, Copyright (c) 2026 Jankees van Woezik. Der untersuchte Stand war
`d37f7781879acaa63179b55673e3ba1f6e0f3bae`. Weder die QML-Dateien noch das
Shell-Skript, Screenshots oder das Font-Awesome-Icon wurden übernommen.
Das neue SVG und das Tray-Symbol sind eigene einfache Zeichnungen.

Die Engine verwendet ausschließlich die CLI von
[rustic](https://github.com/rustic-rs/rustic), unter MIT/Apache-2.0.
rustic wird getrennt installiert, nicht in diesem Repository gebündelt.
Entwickelt und getestet mit rustic **0.11.4**.

| Omarchy-Funktion | Umsetzung in CachyOS KDE |
| --- | --- |
| Ein Symbol in der Leiste | Natives Plasma-6-Miniprogramm, direkt in der Leiste oder optional im Systemabschnitt |
| Fehler-/Überfällig-Anzeige | Rotes Symbol, letzte erfolgreiche Sicherung separat gespeichert |
| Panel und mehrere Ziele | An der KDE-Leiste verankertes Plasma-Popup mit Zielauswahl |
| Quellen als Pfad oder Liste | JSON `source`; fehlende Quellen brechen den gesamten Backup-Vorgang ab |
| Geplante und manuelle Backups | systemd-Benutzertimer und dieselbe CLI für GUI/manuellen Aufruf |
| Verschlüsselter Speicher | rustic-Repository mit Passwortdatei oder externem password_command |
| Schlüssel anzeigen / 1Password | CLI und GUI; Secret-Eingabe und 1Password-Export über stdin |
| Ausschlüsse | Native rustic-Globs, deren Vorzeichen sich von üblichen gitignore-Dateien unterscheiden |
| Aufbewahrung | 7 tägliche, 4 wöchentliche, 12 monatliche, 3 jährliche Stände; `forget --prune` |
| Vorbereitungs-/Fehler-Hooks | `pre_command` und `on_failure_command`, mit Zeitlimit |
| Snapshot-Auswahl und Dateibrowser | Browser im Plasma-Popup: Datum/ID, Ordnernavigation, Filter |
| Restore ohne Überschreiben | Neuer privater Unterordner pro Vorgang unter `~/Restored` |
| Benachrichtigung und Dateimanager | Freedesktop-Benachrichtigung; Aktion öffnet Ordner, Popup öffnet Ziel in Dolphin |
| Protokoll, Integritätsprüfung, Testlauf | GUI/CLI; Protokolle 30 Tage, rustic check, rustic --dry-run |

Ab Version 0.2.0 ist die Standardoberfläche ein natives Plasma-6-QML-Miniprogramm.
Plasma übernimmt Popup-Verankerung, Theme, Skalierung und Wayland-Integration.
Der Python-Dienst stellt eine schmale Sitzungs-D-Bus-Schnittstelle bereit;
Repository-Zugriffe bleiben CLI-Unterprozesse außerhalb von plasmashell.
Das optionale bisherige Qt-Hauptfenster ist mit `gui --window` erreichbar.
Autostart ist ein benutzerspezifischer KDE-Desktop-Eintrag und im Popup schaltbar.
Backup-Zeitpläne bleiben davon unabhängig. Quickshell/Waybar/Hyprland sind nicht nötig.

KDE-Referenzen:
- [Plasma 6 Portierung](https://develop.kde.org/docs/plasma/widget/porting_kf6/)
- [Plasma-Scripting](https://develop.kde.org/docs/plasma/scripting/api/)
- [Nativer QML-D-Bus-Client](https://github.com/KDE/plasma-workspace/tree/master/components/dbus)

Wichtige Engine-Unterschiede:

- `rustic snapshots --json` kann nach Host/Pfaden gruppierte Listen liefern.
- `rustic ls --json` liefert Pfade, keine restic-artigen Metadatenobjekte.
  Der Browser liest deshalb `rustic cat tree ID:/pfad` und nutzt die Nodes.
- Restore verwendet `rustic restore ID:/pfad ZIEL`; es gibt kein restic-`--target`.
- Statistik kommt aus `rustic repoinfo --json --only-files`.
- Native SFTP/S3-Backends werden über `opendal:*` und Backend-Optionen eingerichtet.
- Es wird kein restic-Prozess gestartet. Ein optionaler rclone-Backendhelfer heißt
  in rustic intern `rclone serve restic`; das ist das Transportprotokoll, kein
  Einsatz des restic-Backup-Programms.
