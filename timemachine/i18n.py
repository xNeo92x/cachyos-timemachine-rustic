"""Shared German/English catalog for Qt, Plasma and headless operations."""

import locale
import os
import re

CHOICES = ("system", "de", "en")
EN = {
    "Wiederherstellen …": "Restore …",
    "Weitere Aktionen …": "More actions …",
    "Warte auf Fortschrittsdaten …": "Waiting for progress data …",
    "Verarbeitet: {p0} / {p1}": "Processed: {p0} / {p1}",
    "Verarbeitet: {p0} · Gesamtgröße wird ermittelt …": "Processed: {p0} · calculating total size …",
    "Verarbeitung (Ø): {p0}": "Processing (avg.): {p0}",
    "Repository-Schreiben: {p0}": "Repository writes: {p0}",
    "nas_backend muss buffered oder local sein.": "nas_backend must be buffered or local.",
    "Verstrichen: {p0}": "Elapsed: {p0}",
    "Verbleibend: ca. {p0}": "Remaining: about {p0}",
    "Verarbeitung: Durchschnitt der Quelldaten seit Beginn dieser Phase, einschließlich unveränderter Dateien. Repository-Schreiben: verschlüsselte und komprimierte Pack-Daten, die an das NAS-Dateisystem geschrieben wurden, über etwa 10 Sekunden gemittelt. Kein Messwert der physischen Netzwerkverbindung.": "Processing: average source bytes since this phase began, including unchanged files. Repository writes: encrypted and compressed pack bytes written to the NAS filesystem, averaged over about 10 seconds. This does not measure physical network traffic.",
    "Backup-Laufwerk": "Backup drive",
    "Backup-Passwort · {p0}": "Backup password · {p0}",
    "Protokoll · {p0}": "Log · {p0}",
    "language muss system, de oder en sein.": "language must be system, de or en.",
    "Noch nie": "Never",
    "Sicherung läuft": "Backing up",
    "Wiederherstellung läuft": "Restoring",
    "Repository wird geprüft": "Checking repository",
    "Alte Sicherungen werden bereinigt": "Removing old backups",
    "Repository wird eingerichtet": "Setting up repository",
    "Testlauf": "Dry run",
    "Statistik wird gelesen": "Reading statistics",
    "Vorgang läuft": "Operation in progress",
    "Letztes Backup fehlgeschlagen": "Last backup failed",
    "Fehler / Vorgang unterbrochen": "Error / operation interrupted",
    "Sicherung erfolgreich · Bereinigung fehlgeschlagen": "Backup successful · cleanup failed",
    "Einrichtung erforderlich": "Setup required",
    "Letzte Sicherung ist überfällig": "Last backup is overdue",
    "Bereit": "Ready",
    "Deine Dateien sind gesichert": "Your files are backed up",
    "Vorgang fehlgeschlagen.": "Operation failed.",
    "Time Machine einrichten": "Set up Time Machine",
    "Bei der KDE-Anmeldung automatisch starten": "Start automatically when logging into KDE",
    "Systemintegration": "System integration",
    "Sprache": "Language",
    "Systemsprache verwenden": "Use system language",
    "Die Sprache wird beim Speichern sofort übernommen. Andere Systemsprachen verwenden Englisch.": "The language changes immediately when saved. Other system languages use English.",
    "Speichern": "Save",
    "Quellen (ein Pfad pro Zeile)": "Sources (one path per line)",
    "Backup-Ziele": "Backup destinations",
    "Ziel hinzufügen": "Add destination",
    "Ziel entfernen": "Remove destination",
    "Interner Name": "Internal name",
    "z. B. nas": "e.g. nas",
    "Anzeigename": "Display name",
    "z. B. Synology NAS": "e.g. Synology NAS",
    "Lokaler Ordner oder smb://server/freigabe/backup": "Local folder or smb://server/share/backup",
    "Vor Backup ausführen": "Run before backup",
    "Optional: Laufwerk einhängen oder NAS wecken": "Optional: mount a drive or wake the NAS",
    "Bei Fehler ausführen": "Run on failure",
    "Optionaler eigener Befehl": "Optional custom command",
    "Ordner auswählen …": "Choose folder …",
    "NAS / Netzwerk …": "NAS / network …",
    "Zeitplan": "Schedule",
    "Backend-Optionen (JSON)": "Backend options (JSON)",
    "NAS / Netzwerk: SMB-Freigabe und Backup-Ordner auswählen. Zugang in KDE Wallet speichern.\nSFTP: opendal:sftp mit user, endpoint, root. Cloud: opendal:s3. Details siehe README.": "NAS / network: choose an SMB share and backup folder. Save credentials in KDE Wallet.\nSFTP: opendal:sftp with user, endpoint, root. Cloud: opendal:s3. See README for details.",
    "Quellen & Ziele": "Sources & destinations",
    "Täglich behalten": "Daily backups to keep",
    "Wöchentlich behalten": "Weekly backups to keep",
    "Monatlich behalten": "Monthly backups to keep",
    "Jährlich behalten": "Yearly backups to keep",
    "Überfällig nach (Stunden)": "Overdue after (hours)",
    "Ausschlüsse (rustic-Globs)": "Exclusions (rustic globs)",
    "Beispiel: !.cache/   ·   !Downloads/   ·   !*.iso\n! schließt aus. Positive Muster schließen ein.": "Example: !.cache/   ·   !Downloads/   ·   !*.iso\n! excludes. Positive patterns include.",
    "Aufbewahrung & Ausschlüsse": "Retention & exclusions",
    "Weitere Optionen (env_file, password_command, Ziel-Aufbewahrung)\nkönnen direkt in config.json bearbeitet werden.": "Additional options (env_file, password_command, per-destination retention)\ncan be edited directly in config.json.",
    "config.json im Editor öffnen": "Open config.json in editor",
    "Danach diesen Dialog schließen und im Hauptfenster „Neu laden“ wählen.\nEigene Hook-Befehle werden als dein Benutzer ausgeführt.": "Then close this dialog and choose Reload in the main window.\nCustom hook commands run as your user.",
    "Erweitert": "Advanced",
    "Dateien ausschließen …": "Exclude files …",
    "Dateien auswählen …": "Choose files …",
    "Ordner ausschließen …": "Exclude folders …",
    "Ordner auswählen": "Choose folder",
    "Dateien auswählen": "Choose files",
    "Für Quellen und Ausschlüsse bitte lokale oder eingehängte Dateien und Ordner auswählen.": "For sources and exclusions, choose local or mounted files and folders.",
    "Pfade mit Zeilenumbrüchen werden in Pfad- und Musterlisten nicht unterstützt.": "Paths containing line breaks are not supported in path and pattern lists.",
    "NAS-Backup-Ordner auswählen": "Choose NAS backup folder",
    "Backup-Repository auswählen": "Choose backup repository",
    "Backend-Optionen sind kein gültiges JSON. Änderung wird beim Speichern erneut geprüft.": "Backend options are not valid JSON. Changes will be checked again when saved.",
    "Bitte zuerst Backend-Optionen korrigieren.": "Please correct the backend options first.",
    "Backup-Passwort · ": "Backup password · ",
    "Eigenes Passwort (optional)": "Custom password (optional)",
    "Passwort wiederholen": "Repeat password",
    "Passwort speichern": "Save password",
    "Anzeigen / verbergen": "Show / hide",
    "In 1Password sichern": "Save to 1Password",
    "Schließen": "Close",
    "Ein Passwort ist gespeichert. Bewahre es auch außerhalb dieses PCs auf.": "A password is saved. Keep a copy outside this PC as well.",
    "Das Passwort wird über password_command verwaltet.": "The password is managed using password_command.",
    "Ein eigenes Passwort ist optional. Ohne Passwort können Personen mit Zugriff auf das Repository die Sicherungen lesen.\nFür eine Sicherung ohne Passwort dieses Fenster einfach schließen.": "A custom password is optional. Without a password, anyone with access to the repository can read the backups.\nTo back up without a password, simply close this window.",
    "Für eine Sicherung ohne eigenes Passwort dieses Fenster schließen.": "To back up without a custom password, close this window.",
    "Passwörter stimmen nicht überein.": "Passwords do not match.",
    "Passwort gespeichert.": "Password saved.",
    "In 1Password gesichert.": "Saved to 1Password.",
    "Passwort konnte nicht gespeichert werden.": "Could not save password.",
    "Dateien aus einer Sicherung wiederherstellen": "Restore files from a backup",
    "Zurück zu deinen Dateien": "Back to your files",
    "Wurzel": "Root",
    "Nach oben": "Up",
    "Dateien filtern …": "Filter files …",
    "Größe": "Size",
    "Geändert": "Modified",
    "Sicherungen werden gelesen …": "Reading backups …",
    "Auswahl wiederherstellen": "Restore selection",
    "Diesen Ordner wiederherstellen": "Restore this folder",
    "Sicherungen konnten nicht gelesen werden.": "Could not read backups.",
    "Noch keine Sicherungen vorhanden.": "No backups yet.",
    "Verzeichnis wird gelesen …": "Reading folder …",
    "Verzeichnis konnte nicht gelesen werden.": "Could not read folder.",
    "\nMit „Wurzel“ kannst du die Sicherung von oben durchsuchen.": "\nUse Root to browse the backup from the top.",
    "{p0} Einträge · Wiederherstellung in einen neuen Ordner unter ~/Restored": "{p0} entries · restores into a new folder under ~/Restored",
    "Ordner": "Folder",
    "Wiederherstellung läuft. Fortschritt im Hauptfenster.": "Restoring. Progress is shown in the main window.",
    "Wiederhergestellt: ": "Restored: ",
    "Wiederherstellung fehlgeschlagen.": "Restore failed.",
    "Deine Dateien. Jeder Tag. Ein sicherer Weg zurück.": "Your files. Every day. A safe way back.",
    "Einstellungen": "Settings",
    "Neu laden": "Reload",
    "Zeitpläne aktivieren": "Enable schedules",
    "Zeitpläne pausieren": "Pause schedules",
    "Jetzt sichern": "Back up now",
    "Dateien wiederherstellen": "Restore files",
    "Prüfen": "Check",
    "Abbrechen": "Cancel",
    "Schlüssel": "Password",
    "Repository initialisieren": "Initialize repository",
    "Protokoll": "Log",
    "Version {p0} · Verschlüsselt und dedupliziert mit rustic": "Version {p0} · encrypted and deduplicated with rustic",
    "Zeitpläne": "Schedules",
    "Zeitpläne aktiviert.": "Schedules enabled.",
    "Zeitpläne pausiert.": "Schedules paused.",
    "Zeitpläne konnten nicht angepasst werden.": "Could not update schedules.",
    "Time Machine öffnen": "Open Time Machine",
    "Repository prüfen": "Check repository",
    "Beenden": "Quit",
    "Letzte erfolgreiche Sicherung: ": "Last successful backup: ",
    "\nLetzte Prüfung: ": "\nLast check: ",
    "\nZeitplan: ": "\nSchedule: ",
    "Nur auf Anfrage": "On demand only",
    " · aktiviert": " · enabled",
    " · pausiert / noch nicht installiert": " · paused / not installed yet",
    "   ·   Gespeichert: ": "   ·   Stored: ",
    "Bitte laufende Vorgänge zuerst abschließen oder abbrechen.": "Please finish or cancel running operations first.",
    "Protokoll · ": "Log · ",
    "Noch keine Protokolle vorhanden.": "No logs yet.",
    "Es laufen noch Vorgänge. Bitte zuerst abschließen oder abbrechen.": "Operations are still running. Please finish or cancel them first.",
    "Time Machine läuft bereits im KDE-Systemabschnitt.": "Time Machine is already running in the KDE system tray.",
    "Konfiguration fehlerhaft": "Invalid configuration",
    "Nur manuell": "Manual only",
    "Stündlich": "Hourly",
    "Täglich": "Daily",
    "Wöchentlich": "Weekly",
    "Monatlich": "Monthly",
    "Jährlich": "Yearly",
    "Benutzerdefiniert (systemd)": "Custom (systemd)",
    "Häufigkeit": "Frequency",
    "Uhrzeit": "Time",
    "Minute jeder Stunde": "Minute of each hour",
    "Montag": "Monday", "Dienstag": "Tuesday", "Mittwoch": "Wednesday",
    "Donnerstag": "Thursday", "Freitag": "Friday", "Samstag": "Saturday", "Sonntag": "Sunday",
    "Wochentag": "Weekday",
    "Januar": "January", "Februar": "February", "März": "March", "Mai": "May",
    "Juni": "June", "Juli": "July", "Oktober": "October", "Dezember": "December",
    "Monat": "Month",
    "Tag im Monat": "Day of month",
    "z. B. Mon..Fri *-*-* 08:00:00": "e.g. Mon..Fri *-*-* 08:00:00",
    "Kalenderausdruck": "Calendar expression",
    "Uhrzeiten gelten in der lokalen Zeitzone.": "Times use the local time zone.",
    "Sicherungen werden nur auf Anfrage gestartet.": "Backups only start on demand.",
    "Bestehende besondere Zeitpläne bleiben unverändert.": "Existing custom schedules are preserved.",
    " In Monaten ohne diesen Tag entfällt der Lauf.": " The backup is skipped in months without this day.",
    " Der 29. Februar kommt nur in Schaltjahren vor.": " February 29 only occurs in leap years.",
    "Vorgang gestartet …": "Operation started …",
    "Vorgang abgeschlossen.": "Operation completed.",
    "Wiederherstellung läuft …": "Restoring …",
    "Verschlüsselte Backups mit rustic": "Encrypted backups with rustic",
    "Zurück": "Back",
    "\nBitte python install.py ausführen.": "\nPlease run python install.py.",
    "Diesen Ordner": "This folder",
    "Noch kein Backup-Ziel eingerichtet": "No backup destination configured yet",
    "Dateien wiederherstellen …": "Restore files …",
    "Passwort …": "Password …",
    "Initialisieren": "Initialize",
    "Pausieren": "Pause",
    "Autostart bei KDE-Anmeldung": "Start automatically when logging into KDE",
    "Konfiguration muss ein JSON-Objekt sein.": "Configuration must be a JSON object.",
    "source muss ein Pfad oder eine nicht leere Pfadliste sein.": "source must be a path or a nonempty list of paths.",
    "Mindestens ein Backup-Ziel ist erforderlich.": "At least one backup destination is required.",
    "Jedes Ziel muss ein Objekt sein.": "Each destination must be an object.",
    "Zielnamen müssen eindeutig sein und nur Buchstaben, Ziffern, _ oder - enthalten.": "Destination names must be unique and contain only letters, digits, _ or -.",
    "Repository fehlt für {p0}.": "Repository is missing for {p0}.",
    "restic-URLs werden nicht übernommen. Nutze opendal:sftp / opendal:s3 mit options oder rclone:remote:path.": "restic URLs are not supported. Use opendal:sftp / opendal:s3 with options, or rclone:remote:path.",
    "Ungültiger Wert für {p0}.{p1}.": "Invalid value for {p0}.{p1}.",
    "{p0} muss ein Objekt mit Zeichenketten sein.": "{p0} must be an object containing strings.",
    "exclude_file muss eine Zeichenkette sein.": "exclude_file must be a string.",
    "password_command muss ein nicht leerer Befehl sein.": "password_command must be a nonempty command.",
    "Nutze password_file oder password_command, nicht beide.": "Use either password_file or password_command, not both.",
    "Aufbewahrung benötigt mindestens eine positive Anzahl daily/weekly/monthly/yearly.": "Retention requires at least one positive daily/weekly/monthly/yearly count.",
    "Ungültiger Wert für {p0}.": "Invalid value for {p0}.",
    "Ungültige Snapshot-ID.": "Invalid snapshot ID.",
    "Snapshot-Pfad muss absolut sein und darf kein .. enthalten.": "Snapshot path must be absolute and must not contain .. .",
    "Unbekanntes Backup-Ziel: {p0}": "Unknown backup destination: {p0}",
    "Ungültige Datei {p0}: {p1}": "Invalid file {p0}: {p1}",
    "Dieses Ziel nutzt password_command. Verwalte den Schlüssel dort.": "This destination uses password_command. Manage the password there.",
    "Passwort darf nicht leer sein und keine Zeilenumbrüche enthalten.": "Password must not be empty or contain line breaks.",
    "Schlüssel existiert bereits. Ein Austausch ändert das Repository-Passwort nicht.": "A password is already saved. Replacing the file does not change the repository password.",
    "Passwortänderung nicht bestätigt. Neues Passwort zur Wiederherstellung in {p0}. {p1}": "Password change could not be confirmed. The new recovery password is saved in {p0}. {p1}",
    "Schlüssel wird extern über password_command verwaltet.": "Password is managed externally using password_command.",
    "Noch kein Schlüssel gespeichert.": "No password saved yet.",
    "In 1Password existiert bereits ein Eintrag mit diesem Titel.": "An item with this title already exists in 1Password.",
    "Vorgang wurde unterbrochen (z. B. Neustart).": "Operation was interrupted (e.g. by a restart).",
    "Kein laufender Vorgang für dieses Ziel.": "No operation is running for this destination.",
    "Für dieses Ziel/Repository läuft bereits ein Vorgang.": "An operation is already running for this destination/repository.",
    "env_file muss ein JSON-Objekt mit Zeichenketten enthalten.": "env_file must contain a JSON object with string values.",
    "Die ausdrücklich konfigurierte Passwortdatei fehlt. Bitte wiederherstellen oder den Pfad korrigieren.": "The explicitly configured password file is missing. Please restore it or correct the path.",
    "Schlüsseldatei ist zu offen. Bitte chmod 600 {p0}": "Password file permissions are too open. Please run chmod 600 {p0}",
    "Vorgang abgebrochen.": "Operation cancelled.",
    "rustic wurde nicht gefunden. Bitte rustic installieren.": "rustic was not found. Please install rustic.",
    "Zeitlimit überschritten; Ziel möglicherweise nicht erreichbar.": "Timed out; the destination may be unreachable.",
    "Ausgabe zu groß (32 MiB). Es werden keine unvollständigen Listen angezeigt.": "Output too large (32 MiB). Incomplete lists will not be displayed.",
    "Einzelne Ausgabezeile zu groß.": "Single output line too large.",
    "Befehl fehlgeschlagen (Exit {p0}).": "Command failed (exit {p0}).",
    "keine Liste": "not a list",
    "Unerwartete Snapshot-Ausgabe von rustic.": "Unexpected snapshot output from rustic.",
    "ungültiger Dateiname": "invalid filename",
    "Unerwartete Verzeichnis-Ausgabe von rustic.": "Unexpected directory output from rustic.",
    "Unerwartete Repository-Statistik.": "Unexpected repository statistics.",
    "rustic meldete Warnungen bei der Prüfung; siehe Protokoll.": "rustic reported warnings during the check; see the log.",
    "Backup-Quelle fehlt: {p0}": "Backup source is missing: {p0}",
    "Ausschlussdatei fehlt: {p0}": "Exclusion file is missing: {p0}",
    "rustic meldete Warnungen. Sicherung gilt nicht als vollständig; Aufbewahrung wurde nicht ausgeführt. Siehe Protokoll.": "rustic reported warnings. The backup is not considered complete; retention was skipped. See the log.",
    "rustic bestätigte keinen neuen Snapshot. Bitte Version und Protokoll prüfen.": "rustic did not confirm a new snapshot. Please check the version and log.",
    "rustic meldete Warnungen bei der Bereinigung; siehe Protokoll.": "rustic reported warnings during cleanup; see the log.",
    "Aufbewahrung fehlgeschlagen: {p0}": "Retention failed: {p0}",
    "Statistik nicht aktualisiert: {p0}": "Statistics not updated: {p0}",
    "Backup fehlgeschlagen": "Backup failed",
    "open=In Dolphin öffnen": "open=Open in Dolphin",
    "Wiederherstellung abgeschlossen": "Restore completed",
    "Ungültiger Zeitplan für {p0}: {p1}": "Invalid schedule for {p0}: {p1}",
    "Ungültige Optionen.": "Invalid options.",
    "Unbekannte Aktion.": "Unknown action.",
    "Snapshot und Pfad erforderlich.": "Snapshot and path are required.",
    "Ungültiges Wiederherstellungsziel.": "Invalid restore destination.",
    "Zu viele laufende Anfragen.": "Too many requests in progress.",
    "Anfrage nicht mehr vorhanden.": "Request no longer available.",
    "Unbekannter Dialog.": "Unknown dialog.",
    "Es laufen noch Vorgänge.": "Operations are still running.",
    "Keine KDE-Sitzung erreichbar.": "No KDE session is available.",
    "Der Hintergrunddienst konnte nicht starten. Details: desktop-service.log im Time-Machine-Statusordner.": "The background service could not start. See desktop-service.log in the Time Machine state directory.",
    "Keine D-Bus-Sitzung erreichbar.": "No D-Bus session is available.",
    "NAS-Passwörter bitte in KDE Wallet speichern, nicht in der SMB-Adresse.": "Save NAS passwords in KDE Wallet, not in the SMB address.",
    "Bitte einen NAS-Ordner wählen: smb://server/freigabe/backup-ordner": "Please choose a NAS folder: smb://server/share/backup-folder",
    "NAS-Zugriff benötigt eine laufende KDE-Benutzersitzung (Sitzungs-D-Bus).": "NAS access requires a running KDE user session (session D-Bus).",
    "NAS nicht erreichbar. Freigabe in Dolphin öffnen und Zugang in KDE Wallet speichern. Benötigte Pakete: kio-fuse und kio-extras. ": "NAS is unreachable. Open the share in Dolphin and save credentials in KDE Wallet. Required packages: kio-fuse and kio-extras. ",
    "KDE hat keinen gültigen NAS-Pfad zurückgegeben.": "KDE returned an invalid NAS path.",
    "KDE hat keinen absoluten NAS-Pfad zurückgegeben.": "KDE did not return an absolute NAS path.",
    "NAS ist nicht als KDE-Netzwerkdateisystem verbunden; Vorgang abgebrochen.": "NAS is not connected as a KDE network filesystem; operation cancelled.",
    "NAS-Verzeichnis nicht verfügbar; es wird kein lokales Ersatz-Backup angelegt.": "NAS folder is unavailable; no local replacement backup will be created.",
    "Für die KDE-Dateiauswahl bitte installieren: sudo pacman -S kdialog": "For KDE file selection, please install: sudo pacman -S kdialog",
    "Die KDE-Dateiauswahl konnte nicht gestartet werden. Bitte kdialog prüfen.": "Could not start KDE file selection. Please check kdialog.",
    "Die KDE-Dateiauswahl wurde unerwartet beendet. Deine Eingaben bleiben erhalten.": "KDE file selection closed unexpectedly. Your input is preserved.",
    "Die Dateiauswahl hat einen ungültigen Pfad zurückgegeben.": "File selection returned an invalid path.",
    "Backup-Passwort: ": "Backup password: ",
    "Wiederholen: ": "Repeat: ",
}


def system_language(environ=None):
    env = os.environ if environ is None else environ
    # KDE exports its ordered translation preferences in LANGUAGE. C/POSIX
    # explicitly selects the English fallback, as with GNU gettext.
    base = env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or locale.getlocale()[0] or "C"
    if base.split(".")[0] in ("C", "POSIX"):
        return "en"
    preferred = env.get("LANGUAGE", "").split(":") if env.get("LANGUAGE") else [base]
    for name in preferred:
        code = re.split(r"[_\-.@]", name.lower())[0]
        if code in ("de", "en"):
            return code
    return "en"


_language = system_language()


def configure(choice="system"):
    global _language
    _language = choice if choice in ("de", "en") else system_language()
    return _language


def language():
    return _language


def tr(source, **values):
    text = EN.get(source, source) if _language == "en" else source
    return text.format(**values) if values else text


def _binding(text):
    """Remember source templates once; never translate editable values or paths."""
    for source, translated in EN.items():
        for pattern in (source, translated):
            parts = re.split(r"(\{p\d+\})", pattern)
            regex = "".join("(.*?)" if re.fullmatch(r"\{p\d+\}", p) else re.escape(p) for p in parts)
            match = re.fullmatch(regex, text, re.DOTALL)
            if match:
                names = [p[1:-1] for p in parts if re.fullmatch(r"\{p\d+\}", p)]
                return source, dict(zip(names, match.groups(), strict=True))
    return None


def translate_message(text):
    """Localize known stored errors; leave rustic output and paths intact."""
    binding = _binding(text) if isinstance(text, str) and text else None
    return tr(binding[0], **binding[1]) if binding else text


def bind_ui(root):
    """Capture static Qt text at construction, before dynamic data is populated."""
    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QComboBox, QDialogButtonBox, QLabel, QLineEdit, QTabWidget, QTreeWidget

    for obj in [root, *root.findChildren(QObject)]:
        if hasattr(obj, "_language_bindings"):
            continue
        bindings = []
        properties = ["windowTitle", "toolTip"]
        if (isinstance(obj, QLabel) and not obj.property("dynamicLanguage")) or obj.inherits("QAbstractButton") or obj.inherits("QAction"):
            properties.append("text")
        if isinstance(obj, QLineEdit):
            properties.append("placeholderText")  # Never touch user-entered text.
        for prop in properties:
            value = obj.property(prop)
            binding = _binding(value) if isinstance(value, str) and value else None
            if binding:
                bindings.append((prop, None, binding))
        if isinstance(obj, (QComboBox, QTabWidget)):
            for index in range(obj.count()):
                value = obj.itemText(index) if isinstance(obj, QComboBox) else obj.tabText(index)
                binding = _binding(value)
                if binding:
                    bindings.append(("item" if isinstance(obj, QComboBox) else "tab", index, binding))
        if isinstance(obj, QTreeWidget):
            for index in range(obj.columnCount()):
                binding = _binding(obj.headerItem().text(index))
                if binding:
                    bindings.append(("header", index, binding))
        if isinstance(obj, QDialogButtonBox):
            for standard, source in ((QDialogButtonBox.StandardButton.Save, "Speichern"),
                                     (QDialogButtonBox.StandardButton.Cancel, "Abbrechen")):
                btn = obj.button(standard)
                if btn:
                    btn._language_bindings = [("text", None, (source, {}))]
                    btn.setText(tr(source))
        obj._language_bindings = bindings


def apply_ui_language(root):
    from PySide6.QtCore import QObject

    for obj in [root, *root.findChildren(QObject)]:
        blocked = obj.blockSignals(True)
        try:
            for prop, index, (source, values) in getattr(obj, "_language_bindings", []):
                text = tr(source, **values)
                if prop == "item":
                    obj.setItemText(index, text)
                elif prop == "tab":
                    obj.setTabText(index, text)
                elif prop == "header":
                    obj.headerItem().setText(index, text)
                else:
                    obj.setProperty(prop, text)
        finally:
            obj.blockSignals(blocked)


def configure_qt():
    """Translate Qt's own controls and localize dates without changing process LANG."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    QLocale.setDefault(QLocale("de_DE" if _language == "de" else "en_US"))
    previous = getattr(app, "_qt_language_translator", None)
    if previous:
        app.removeTranslator(previous)
        previous.deleteLater()
    translator = QTranslator(app)
    if _language == "de" and translator.load("qtbase_de", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    app._qt_language_translator = translator
