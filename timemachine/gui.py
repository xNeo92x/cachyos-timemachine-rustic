"""Native Qt 6 desktop UI. QSystemTrayIcon becomes a KDE StatusNotifierItem."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QDateTime, QLocale, QLockFile, QProcess, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .core import APP, RETENTION, Engine, Error, atomic, validate
from .filepicker import FilePicker
from .i18n import apply_ui_language, bind_ui, configure_qt, language, tr, translate_message
from .integration import autostart_enabled, set_autostart
from .network import NetworkError, is_smb, mounted_url, smb_url
from .progress import human_size, progress_view
from .schedule import ScheduleEditor


def date(value):
    if not value:
        return tr("Noch nie")
    parsed = QDateTime.fromString(value, Qt.DateFormat.ISODate)
    return QLocale().toString(parsed.toLocalTime(), QLocale.FormatType.ShortFormat) if parsed.isValid() else value


def status_text(row):
    if row.get("status") == "running":
        return {
            "backup": tr("Sicherung läuft"),
            "restore": tr("Wiederherstellung läuft"),
            "check": tr("Repository wird geprüft"),
            "retention": tr("Alte Sicherungen werden bereinigt"),
            "init": tr("Repository wird eingerichtet"),
            "dry-run": tr("Testlauf"),
            "stats": tr("Statistik wird gelesen"),
        }.get(row.get("phase"), tr("Vorgang läuft"))
    if row.get("last_backup_status") == "failed":
        return tr("Letztes Backup fehlgeschlagen")
    if row.get("status") in ("failed", "interrupted"):
        return tr("Fehler / Vorgang unterbrochen")
    if row.get("maintenance_error"):
        return tr("Sicherung erfolgreich · Bereinigung fehlgeschlagen")
    if not row.get("can_backup", row.get("has_key")):
        return tr("Einrichtung erforderlich")
    if row.get("stale"):
        return tr("Letzte Sicherung ist überfällig")
    return tr("Bereit") if not row.get("last_success") else tr("Deine Dateien sind gesichert")


def tray_icon(color):
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawArc(12, 12, 42, 42, 40 * 16, 285 * 16)
    painter.drawLine(13, 13, 13, 27)
    painter.drawLine(13, 27, 27, 27)
    painter.drawLine(33, 23, 33, 34)
    painter.drawLine(33, 34, 42, 39)
    painter.end()
    return QIcon(pixmap)


def button(text, callback, icon=None):
    result = QPushButton(text)
    result.setAutoDefault(False)
    if icon:
        result.setIcon(QIcon.fromTheme(icon))
    result.clicked.connect(callback)
    return result


class Jobs:
    """Qt-managed child processes keep all repository access off the UI thread."""

    def __init__(self, window):
        self.window = window
        self.processes = set()

    def start(self, args, callback=None, secret=None):
        process = QProcess(self.window)
        self.processes.add(process)
        command = [
            "-m",
            "timemachine.cli",
            "--config-dir",
            str(self.window.config_dir),
            "--state-dir",
            str(self.window.state_dir),
            *args,
        ]
        process.setProgram(sys.executable)
        process.setArguments(command)

        def done(*_):
            if process not in self.processes:
                return
            self.processes.discard(process)
            raw = bytes(process.readAllStandardOutput()).decode("utf-8", "replace").strip()
            err = bytes(process.readAllStandardError()).decode("utf-8", "replace").strip()
            try:
                result = json.loads(raw)
            except ValueError:
                result = {"ok": False, "error": err or raw or process.errorString()}
            if callback:
                callback(result)
            elif not result.get("ok"):
                self.window.error(result.get("error", tr("Vorgang fehlgeschlagen.")))
            self.window.refresh()
            process.deleteLater()

        process.finished.connect(done)
        process.errorOccurred.connect(
            lambda error: done() if error == QProcess.ProcessError.FailedToStart else None
        )
        process.start()
        if secret is not None:
            process.write((secret + "\n").encode())
        process.closeWriteChannel()
        return process


class Settings(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Time Machine einrichten"))
        self.resize(780, 700)
        self.config = json.loads(json.dumps(window.engine.config))
        self.index = None
        self.file_picker = None
        self.browse_directory = str(Path.home())
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        basic = QWidget()
        form = QFormLayout(basic)
        self.autostart = QCheckBox(tr("Bei der KDE-Anmeldung automatisch starten"))
        self.autostart.setChecked(autostart_enabled())
        form.addRow(tr("Systemintegration"), self.autostart)
        self.language = QComboBox()
        self.language.addItem(tr("Systemsprache verwenden"), "system")
        self.language.addItem("Deutsch", "de")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(self.config.get("language", "system")))
        form.addRow(tr("Sprache"), self.language)
        language_note = QLabel(tr("Die Sprache wird beim Speichern sofort übernommen. Andere Systemsprachen verwenden Englisch."))
        language_note.setWordWrap(True)
        form.addRow(language_note)
        self.sources = QPlainTextEdit()
        source = self.config.get("source", "~")
        self.sources.setPlainText("\n".join([source] if isinstance(source, str) else source))
        self.sources.setMaximumHeight(85)
        form.addRow(tr("Quellen (ein Pfad pro Zeile)"), self.sources)
        form.addRow(self.path_buttons(self.sources))
        self.destinations = QListWidget()
        self.destinations.setMaximumHeight(95)
        form.addRow(tr("Backup-Ziele"), self.destinations)
        actions = QHBoxLayout()
        actions.addWidget(button(tr("Ziel hinzufügen"), self.add_dest, "list-add"))
        actions.addWidget(button(tr("Ziel entfernen"), self.remove_dest, "list-remove"))
        form.addRow(actions)
        self.fields = {}
        for key, title, hint in [
            ("name", tr("Interner Name"), tr("z. B. nas")),
            ("display_name", tr("Anzeigename"), tr("z. B. Synology NAS")),
            ("repository", "Repository", tr("Lokaler Ordner oder smb://server/freigabe/backup")),
            ("pre_command", tr("Vor Backup ausführen"), tr("Optional: Laufwerk einhängen oder NAS wecken")),
            ("on_failure_command", tr("Bei Fehler ausführen"), tr("Optionaler eigener Befehl")),
        ]:
            edit = QLineEdit()
            edit.setPlaceholderText(hint)
            if key == "repository":
                row = QHBoxLayout()
                row.addWidget(edit)
                row.addWidget(button(tr("Ordner auswählen …"), self.pick_repository, "folder-open"))
                form.addRow(title, row)
                form.addRow("", button(tr("NAS / Netzwerk …"), lambda: self.pick_repository(network=True), "network-server"))
            else:
                form.addRow(title, edit)
            self.fields[key] = edit
        self.schedule = ScheduleEditor()
        form.addRow(tr("Zeitplan"), self.schedule)
        self.options = QPlainTextEdit()
        self.options.setMaximumHeight(105)
        form.addRow(tr("Backend-Optionen (JSON)"), self.options)
        note = QLabel(
            tr("NAS / Netzwerk: SMB-Freigabe und Backup-Ordner auswählen. Zugang in KDE Wallet speichern.\nSFTP: opendal:sftp mit user, endpoint, root. Cloud: opendal:s3. Details siehe README.")
        )
        note.setWordWrap(True)
        form.addRow(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(basic)
        tabs.addTab(scroll, tr("Quellen & Ziele"))
        policies = QWidget()
        pf = QFormLayout(policies)
        self.retention = {}
        for key, title in [
            ("daily", tr("Täglich behalten")),
            ("weekly", tr("Wöchentlich behalten")),
            ("monthly", tr("Monatlich behalten")),
            ("yearly", tr("Jährlich behalten")),
        ]:
            spin = QSpinBox()
            spin.setRange(0, 10000)
            spin.setValue(self.config.get("retention", RETENTION).get(key, 0))
            self.retention[key] = spin
            pf.addRow(title, spin)
        self.stale = QSpinBox()
        self.stale.setRange(1, 87600)
        self.stale.setValue(int(self.config.get("stale_hours", 48)))
        pf.addRow(tr("Überfällig nach (Stunden)"), self.stale)
        self.excludes = QPlainTextEdit()
        exclude = window.config_dir / self.config.get("exclude_file", "excludes.txt")
        self.excludes.setPlainText(exclude.read_text() if exclude.exists() else "")
        pf.addRow(tr("Ausschlüsse (rustic-Globs)"), self.excludes)
        pf.addRow(self.path_buttons(self.excludes, excluded=True))
        pf.addRow(
            QLabel(
                tr("Beispiel: !.cache/   ·   !Downloads/   ·   !*.iso\n! schließt aus. Positive Muster schließen ein.")
            )
        )
        tabs.addTab(policies, tr("Aufbewahrung & Ausschlüsse"))
        advanced = QWidget()
        av = QVBoxLayout(advanced)
        av.addWidget(
            QLabel(
                tr("Weitere Optionen (env_file, password_command, Ziel-Aufbewahrung)\nkönnen direkt in config.json bearbeitet werden.")
            )
        )
        av.addWidget(
            button(
                tr("config.json im Editor öffnen"),
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(window.engine.config_path))),
                "document-edit",
            )
        )
        av.addWidget(
            QLabel(
                tr("Danach diesen Dialog schließen und im Hauptfenster „Neu laden“ wählen.\nEigene Hook-Befehle werden als dein Benutzer ausgeführt.")
            )
        )
        av.addStretch()
        tabs.addTab(advanced, tr("Erweitert"))
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        for action in box.buttons():
            action.setAutoDefault(False)
            action.setDefault(False)
        box.accepted.connect(self.save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.destinations.currentRowChanged.connect(self.select_dest)
        self.rebuild()
        bind_ui(self)

    def path_buttons(self, editor, excluded=False):
        row = QHBoxLayout()
        row.addWidget(
            button(
                tr("Dateien ausschließen …") if excluded else tr("Dateien auswählen …"),
                lambda: self.pick_paths(editor, excluded=excluded),
                "document-open",
            )
        )
        row.addWidget(
            button(
                tr("Ordner ausschließen …") if excluded else tr("Ordner auswählen …"),
                lambda: self.pick_paths(editor, directory=True, excluded=excluded),
                "folder-open",
            )
        )
        return row

    def choose_paths(self, title, start, directory, selected):
        if self.file_picker is not None:
            return
        picker = FilePicker()
        self.file_picker = picker
        self.setEnabled(False)

        def completed(paths, error):
            self.file_picker = None
            if picker.cancelled:
                return
            self.setEnabled(True)
            self.raise_()
            self.activateWindow()
            if error:
                self.window.error(error)
            elif paths:
                selected(paths)

        picker.completed.connect(completed)
        picker.start(title, start, directory)

    def done(self, result):
        if self.file_picker is not None:
            self.file_picker.cancel()
        super().done(result)

    def pick_paths(self, editor, directory=False, excluded=False):
        self.choose_paths(
            tr("Ordner auswählen") if directory else tr("Dateien auswählen"),
            self.browse_directory, directory,
            lambda paths: self.apply_paths(editor, paths, directory, excluded),
        )

    def apply_paths(self, editor, paths, directory=False, excluded=False):
        if any(not Path(path).is_absolute() for path in paths):
            self.window.error(tr("Für Quellen und Ausschlüsse bitte lokale oder eingehängte Dateien und Ordner auswählen."))
            return
        if not paths:
            return
        if any("\n" in path or "\r" in path for path in paths):
            self.window.error(tr("Pfade mit Zeilenumbrüchen werden in Pfad- und Musterlisten nicht unterstützt."))
            return
        lines = editor.toPlainText().splitlines()
        for path in paths:
            if excluded:
                literal = re.sub(r"([\\*?\[\]{}!])", r"\\\1", path)
                patterns = ["!" + literal]
                if directory:
                    patterns.append("!" + literal.rstrip("/") + "/**")
            else:
                patterns = [path]
            lines.extend(pattern for pattern in patterns if pattern not in lines)
        editor.setPlainText("\n".join(lines))
        self.browse_directory = paths[-1] if directory else str(Path(paths[-1]).parent)

    def pick_repository(self, network=False):
        current = self.fields["repository"].text().strip()
        if is_smb(current):
            start = current
        elif network:
            start = "smb://"
        else:
            start = str(Path(current).expanduser()) if current and ":" not in current else self.browse_directory
        self.choose_paths(
            tr("NAS-Backup-Ordner auswählen") if network else tr("Backup-Repository auswählen"),
            start, True,
            lambda paths: self.apply_repository_url(
                QUrl.fromLocalFile(paths[0]) if Path(paths[0]).is_absolute() else QUrl(paths[0])
            ),
        )

    def apply_repository_url(self, selected):
        if selected.isEmpty():
            return
        try:
            if selected.isLocalFile():
                path = selected.toLocalFile()
                repository = mounted_url(path) or path
                self.browse_directory = path
            else:
                # Credentials belong to KWallet; never persist passwords from a picker URL.
                selected.setPassword(None)
                repository = smb_url(selected.toString(QUrl.ComponentFormattingOption.FullyEncoded))
            self.fields["repository"].setText(repository)
        except (NetworkError, OSError) as exc:
            self.window.error(str(exc))

    def store_dest(self):
        if self.index is None or self.index >= len(self.config["destinations"]):
            return
        dest = self.config["destinations"][self.index]
        for key, edit in self.fields.items():
            value = edit.text().strip()
            if value or key in ("name", "repository"):
                dest[key] = value
            else:
                dest.pop(key, None)
        schedule = self.schedule.schedule()
        if schedule:
            dest["schedule"] = schedule
        else:
            dest.pop("schedule", None)
        options = json.loads(self.options.toPlainText() or "{}")
        if options:
            dest["options"] = options
        else:
            dest.pop("options", None)

    def select_dest(self, index):
        try:
            self.store_dest()
        except ValueError:
            self.window.error(
                tr("Backend-Optionen sind kein gültiges JSON. Änderung wird beim Speichern erneut geprüft.")
            )
        self.index = index if index >= 0 else None
        if self.index is None:
            return
        dest = self.config["destinations"][index]
        for key, edit in self.fields.items():
            edit.setText(dest.get(key, ""))
        self.schedule.set_schedule(dest.get("schedule", ""))
        self.options.setPlainText(json.dumps(dest.get("options", {}), indent=2, ensure_ascii=False))

    def rebuild(self, index=0):
        self.index = None
        self.destinations.blockSignals(True)
        self.destinations.clear()
        self.destinations.addItems([d.get("display_name", d["name"]) for d in self.config["destinations"]])
        self.destinations.blockSignals(False)
        self.destinations.setCurrentRow(index)

    def add_dest(self):
        try:
            self.store_dest()
        except ValueError:
            self.window.error(tr("Bitte zuerst Backend-Optionen korrigieren."))
            return
        count = len(self.config["destinations"]) + 1
        self.config["destinations"].append(
            {"name": f"backup-{count}", "repository": "", "display_name": f"Backup {count}"}
        )
        self.rebuild(count - 1)

    def remove_dest(self):
        if self.index is not None and len(self.config["destinations"]) > 1:
            self.config["destinations"].pop(self.index)
            self.rebuild()

    def save(self):
        try:
            self.store_dest()
            self.config["language"] = self.language.currentData()
            self.config["source"] = [x.strip() for x in self.sources.toPlainText().splitlines() if x.strip()]
            self.config["retention"] = {k: v.value() for k, v in self.retention.items()}
            self.config["stale_hours"] = self.stale.value()
            validate(self.config)
            atomic(self.window.engine.config_path, self.config)
            atomic(
                self.window.config_dir / self.config.get("exclude_file", "excludes.txt"),
                self.excludes.toPlainText(),
            )
        except (Error, ValueError, OSError) as exc:
            self.window.error(str(exc))
            return
        try:
            set_autostart(self.autostart.isChecked())
        except OSError as exc:
            self.window.error(str(exc))
            return
        self.accept()


class KeyDialog(QDialog):
    """Visible, retained password management; no cursor-anchored service menu."""

    def __init__(self, window, name):
        super().__init__(window)
        self.window, self.name = window, name
        self.setWindowTitle(tr("Backup-Passwort · {p0}", p0=window.engine.dest(name).get("display_name", name)))
        self.setMinimumWidth(480)
        self.busy = False
        layout = QVBoxLayout(self)
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText(tr("Eigenes Passwort (optional)"))
        self.repeat = QLineEdit()
        self.repeat.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat.setPlaceholderText(tr("Passwort wiederholen"))
        layout.addWidget(self.password)
        layout.addWidget(self.repeat)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.save_button = button(tr("Passwort speichern"), self.save_password)
        layout.addWidget(self.save_button)
        self.reveal_button = button(tr("Anzeigen / verbergen"), self.reveal)
        layout.addWidget(self.reveal_button)
        self.export_button = button(tr("In 1Password sichern"), self.export_password)
        layout.addWidget(self.export_button)
        self.close_button = button(tr("Schließen"), self.reject)
        layout.addWidget(self.close_button)
        bind_ui(self)
        self.refresh_mode()

    def refresh_mode(self):
        mode = self.window.engine.password_mode(self.window.engine.dest(self.name))
        stored = mode == "stored"
        external = mode == "external"
        self.explanation.setText(
            tr("Ein Passwort ist gespeichert. Bewahre es auch außerhalb dieses PCs auf.")
            if stored else tr("Das Passwort wird über password_command verwaltet.")
            if external else
            tr("Ein eigenes Passwort ist optional. Ohne Passwort können Personen mit Zugriff auf das Repository die Sicherungen lesen.\nFür eine Sicherung ohne Passwort dieses Fenster einfach schließen.")
        )
        self.password.setVisible(not external)
        self.password.setReadOnly(stored)
        self.repeat.setVisible(not stored and not external)
        self.save_button.setVisible(not stored and not external)
        self.reveal_button.setVisible(stored)
        self.export_button.setVisible(stored)
        if stored:
            self.password.setText(self.window.engine.show_key(self.name))
            self.repeat.clear()

    def reveal(self):
        self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if self.password.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )

    def save_password(self):
        password = self.password.text()
        if not password:
            self.message.setText(tr("Für eine Sicherung ohne eigenes Passwort dieses Fenster schließen."))
            return
        if password != self.repeat.text():
            self.message.setText(tr("Passwörter stimmen nicht überein."))
            return
        self.submit(["key", "set", "--dest", self.name, "--stdin"], password)

    def export_password(self):
        self.submit(["key", "save-1password", "--dest", self.name])

    def submit(self, args, secret=None):
        if self.busy:
            return
        self.busy = True
        self.setEnabled(False)

        def ready(result):
            self.busy = False
            self.setEnabled(True)
            if result.get("ok"):
                self.window.reload()
                self.refresh_mode()
                self.message.setText(tr("Passwort gespeichert.") if secret is not None else tr("In 1Password gesichert."))
            else:
                self.message.setText(result.get("error", tr("Passwort konnte nicht gespeichert werden.")))

        self.window.jobs.start(args, ready, secret)

    def reject(self):
        if not self.busy:
            self.password.clear()
            self.repeat.clear()
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            self.password.clear()
            self.repeat.clear()
            super().closeEvent(event)


class RestoreBrowser(QDialog):
    def __init__(self, window, name):
        super().__init__(window)
        self.window, self.name = window, name
        self.path = "/"
        self.request = 0
        self.setWindowTitle(tr("Dateien aus einer Sicherung wiederherstellen"))
        self.resize(940, 640)
        layout = QVBoxLayout(self)
        heading = QLabel(tr("Zurück zu deinen Dateien"))
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self.days = QComboBox()
        self.days.currentIndexChanged.connect(self.load_folder)
        layout.addWidget(self.days)
        navigation = QHBoxLayout()
        navigation.addWidget(button(tr("Nach oben"), self.up, "go-up"))
        navigation.addWidget(button(tr("Wurzel"), self.root, "go-home"))
        self.location = QLineEdit("/")
        self.location.returnPressed.connect(self.go_path)
        navigation.addWidget(self.location, 1)
        layout.addLayout(navigation)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Dateien filtern …"))
        self.filter.textChanged.connect(self.filter_rows)
        layout.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", tr("Größe"), tr("Geändert")])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemActivated.connect(self.open_item)
        self.tree.installEventFilter(self)
        layout.addWidget(self.tree, 1)
        self.message = QLabel(tr("Sicherungen werden gelesen …"))
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        self.restore_selected = button(tr("Auswahl wiederherstellen"), self.restore_item, "document-revert")
        self.restore_folder = button(
            tr("Diesen Ordner wiederherstellen"), lambda: self.restore(self.path), "folder"
        )
        self.restore_selected.setEnabled(False)
        self.restore_folder.setEnabled(False)
        self.tree.itemSelectionChanged.connect(
            lambda: self.restore_selected.setEnabled(self.tree.currentItem() is not None)
        )
        actions.addWidget(self.restore_selected)
        actions.addWidget(self.restore_folder)
        actions.addStretch()
        actions.addWidget(button(tr("Schließen"), self.close))
        layout.addLayout(actions)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self.up)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.filter.setFocus)
        self.message.setProperty("dynamicLanguage", True)
        bind_ui(self)
        window.jobs.start(["snapshots", "--dest", name, "--json"], self.snapshots_ready)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent

        if (
            obj is self.tree
            and event.type() == QEvent.Type.KeyPress
            and event.text().isprintable()
            and event.text()
            and not event.modifiers()
            & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        ):
            self.filter.setFocus()
            self.filter.insert(event.text())
            return True
        return super().eventFilter(obj, event)

    def snapshots_ready(self, result):
        if not result.get("ok"):
            self.message.setText(result.get("error", tr("Sicherungen konnten nicht gelesen werden.")))
            return
        self.days.blockSignals(True)
        for snap in result["snapshots"]:
            self.days.addItem(
                f"{date(snap['time'])}   ·   {snap['id'][:8]}   ·   {snap.get('hostname', '')}", snap
            )
        self.days.blockSignals(False)
        if self.days.count():
            source = result["snapshots"][0].get("paths", [])
            if source and isinstance(source[0], str) and source[0].startswith("/"):
                self.path = source[0]
            self.load_folder()
        else:
            self.message.setText(tr("Noch keine Sicherungen vorhanden."))

    def load_folder(self, *_):
        snapshot = self.days.currentData()
        if not snapshot:
            return
        self.request += 1
        request = self.request
        self.tree.clear()
        self.restore_folder.setEnabled(False)
        self.restore_selected.setEnabled(False)
        self.location.setText(self.path)
        self.message.setText(tr("Verzeichnis wird gelesen …"))

        def ready(result):
            if request != self.request:
                return
            if not result.get("ok"):
                self.message.setText(
                    result.get("error", tr("Verzeichnis konnte nicht gelesen werden."))
                    + tr("\nMit „Wurzel“ kannst du die Sicherung von oben durchsuchen.")
                )
                return
            for node in result["entries"]:
                item = QTreeWidgetItem(
                    [
                        node["name"],
                        human_size(node.get("size")) if node["type"] != "dir" else tr("Ordner"),
                        date(node.get("mtime")) if node.get("mtime") else "–",
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, node)
                item.setIcon(
                    0,
                    QIcon.fromTheme(
                        "folder"
                        if node["type"] == "dir"
                        else "emblem-symbolic-link"
                        if node["type"] == "symlink"
                        else "text-x-generic"
                    ),
                )
                self.tree.addTopLevelItem(item)
            self.filter_rows()
            self.restore_folder.setEnabled(True)
            self.message.setText(
                tr("{p0} Einträge · Wiederherstellung in einen neuen Ordner unter ~/Restored", p0=len(result['entries']))
            )

        self.window.jobs.start(
            ["ls", "--dest", self.name, "--snapshot", snapshot["id"], "--path", self.path, "--json"], ready
        )

    def filter_rows(self):
        text = self.filter.text().casefold()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setHidden(text not in item.text(0).casefold())

    def go_path(self):
        self.path = self.location.text()
        self.load_folder()

    def root(self):
        self.path = "/"
        self.load_folder()

    def up(self):
        self.path = str(PurePosixPath(self.path).parent)
        self.load_folder()

    def open_item(self, item, *_):
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node["type"] == "dir":
            self.path = node["path"]
            self.load_folder()

    def restore_item(self):
        item = self.tree.currentItem()
        if item and not item.isHidden():
            self.restore(item.data(0, Qt.ItemDataRole.UserRole)["path"])

    def restore(self, path):
        snapshot = self.days.currentData()
        self.restore_selected.setEnabled(False)
        self.restore_folder.setEnabled(False)
        self.message.setText(tr("Wiederherstellung läuft. Fortschritt im Hauptfenster."))

        def ready(result):
            self.restore_folder.setEnabled(True)
            self.restore_selected.setEnabled(self.tree.currentItem() is not None)
            if result.get("ok"):
                self.message.setText(tr("Wiederhergestellt: ") + result["restored"])
                QDesktopServices.openUrl(QUrl.fromLocalFile(result["target"]))
            else:
                self.message.setText(result.get("error", tr("Wiederherstellung fehlgeschlagen.")))

        self.window.jobs.start(
            ["restore", "--dest", self.name, "--snapshot", snapshot["id"], "--path", path, "--json"], ready
        )


class Window(QMainWindow):
    def __init__(self, config_dir=None, state_dir=None, native_panel=False):
        super().__init__()
        self.native_panel = native_panel
        self.config_dir = Path(
            config_dir or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
        )
        self.state_dir = Path(
            state_dir or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP
        )
        Engine.create_config(self.config_dir)
        self.engine = Engine(self.config_dir, self.state_dir)
        self.jobs = Jobs(self)
        self.rows = []
        self.last_menu = None
        self.dialogs = []
        self.settings_dialog = None
        self.key_dialog = None
        self.ui_language = None
        self.setWindowTitle("CachyOS Time Machine")
        self.setWindowIcon(tray_icon("#3daee9"))
        self.resize(900, 610)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 22, 24, 22)
        header = QHBoxLayout()
        title = QLabel("Time Machine")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(QLabel("rustic · CachyOS KDE"))
        layout.addLayout(header)
        layout.addWidget(QLabel(tr("Deine Dateien. Jeder Tag. Ein sicherer Weg zurück.")))
        tools = QHBoxLayout()
        tools.addWidget(button(tr("Einstellungen"), self.settings, "configure"))
        tools.addWidget(button(tr("Neu laden"), self.reload, "view-refresh"))
        tools.addWidget(
            button(
                tr("Zeitpläne aktivieren"),
                lambda: self.jobs.start(["install"], self.timers_ready),
                "appointment-new",
            )
        )
        tools.addWidget(
            button(
                tr("Zeitpläne pausieren"),
                lambda: self.jobs.start(["pause"], self.timers_ready),
                "media-playback-pause",
            )
        )
        layout.addLayout(tools)
        split = QSplitter()
        self.list = QListWidget()
        self.list.setMinimumWidth(230)
        self.list.currentRowChanged.connect(self.details)
        split.addWidget(self.list)
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        content = QVBoxLayout(panel)
        content.setContentsMargins(22, 22, 22, 22)
        self.label = QLabel()
        self.label.setObjectName("subheading")
        content.addWidget(self.label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        content.addWidget(self.status_label)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(self.info)
        self.progress = QProgressBar()
        content.addWidget(self.progress)
        self.progress_details = QLabel()
        self.progress_details.setWordWrap(True)
        self.progress_details.setProperty("dynamicLanguage", True)
        content.addWidget(self.progress_details)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("error")
        content.addWidget(self.error_label)
        content.addStretch()
        self.backup_button = button(tr("Jetzt sichern"), lambda: self.action("backup"), "document-save")
        self.restore_button = button(tr("Dateien wiederherstellen"), self.restore, "document-revert")
        content.addWidget(self.backup_button)
        content.addWidget(self.restore_button)
        actions = QHBoxLayout()
        self.check_button = button(tr("Prüfen"), lambda: self.action("check"), "checkmark")
        self.dry_button = button(tr("Testlauf"), lambda: self.action("backup", ["--dry-run"]), "system-run")
        self.cancel_button = button(tr("Abbrechen"), lambda: self.action("cancel"), "process-stop")
        actions.addWidget(self.check_button)
        actions.addWidget(self.dry_button)
        actions.addWidget(self.cancel_button)
        content.addLayout(actions)
        keys = QHBoxLayout()
        keys.addWidget(button(tr("Schlüssel"), self.key_menu, "dialog-password"))
        self.init_button = button(tr("Repository initialisieren"), lambda: self.action("init"), "folder-new")
        keys.addWidget(self.init_button)
        keys.addWidget(button(tr("Protokoll"), self.logs, "view-list-text"))
        content.addLayout(keys)
        split.addWidget(panel)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        footer = QLabel(tr("Version {p0} · Verschlüsselt und dedupliziert mit rustic", p0=__version__))
        footer.setObjectName("footer")
        layout.addWidget(footer)
        # Fonts/spacing only: colors and controls come from the current KDE/Qt theme.
        self.setStyleSheet(
            "QLabel#heading {font-size: 28px; font-weight: 600;} QLabel#subheading {font-size: 20px; font-weight: 600;} QLabel#error {color: #da4453;} QLabel#footer {font-size: 11px;} QPushButton {padding: 7px 10px;} QListWidget::item {padding: 14px 8px;}"
        )
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(tray_icon("#3daee9"))
        self.tray.activated.connect(
            lambda reason: (
                self.toggle()
                if reason
                in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick)
                else None
            )
        )
        if not native_panel:
            self.tray.show()
        bind_ui(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def error(self, text):
        QMessageBox.warning(self, "CachyOS Time Machine", text)

    def timers_ready(self, result):
        if result.get("ok"):
            QMessageBox.information(
                self, tr("Zeitpläne"), tr("Zeitpläne aktiviert.") if result.get("enabled") else tr("Zeitpläne pausiert.")
            )
        else:
            self.error(result.get("error", tr("Zeitpläne konnten nicht angepasst werden.")))

    def reload(self):
        try:
            self.engine = Engine(self.config_dir, self.state_dir)
            self.refresh()
        except (Error, OSError) as exc:
            self.error(str(exc))

    def refresh(self):
        if self.ui_language != language():
            self.ui_language = language()
            configure_qt()
            apply_ui_language(self)
            self.last_menu = None
            if self.key_dialog:
                self.key_dialog.refresh_mode()
            for editor in self.findChildren(ScheduleEditor):
                loading = editor.loading
                editor.loading = True
                editor.changed()
                editor.loading = loading
        try:
            rows = self.engine.status()
        except (Error, OSError) as exc:
            self.statusBar().showMessage(str(exc))
            return
        old_name = self.selected()
        self.rows = rows
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([r["display_name"] + "\n" + status_text(r) for r in rows])
        index = next((i for i, r in enumerate(rows) if r["name"] == old_name), 0)
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)
        self.details()
        running = any(r.get("status") == "running" for r in rows)
        bad = any(
            r.get("last_backup_status") == "failed"
            or r.get("status") in ("failed", "interrupted")
            or r.get("stale")
            or r.get("maintenance_error")
            for r in rows
        )
        configured = all(r.get("can_backup", r.get("has_key")) for r in rows)
        self.tray.setIcon(
            tray_icon(
                "#3daee9"
                if running
                else "#da4453"
                if bad
                else "#f67400"
                if not configured
                else self.palette().text().color().name()
            )
        )
        self.tray.setToolTip(
            "CachyOS Time Machine\n"
            + "\n".join(
                r["display_name"] + ": " + status_text(r) + " · " + date(r.get("last_success")) for r in rows
            )
        )
        signature = tuple((r["name"], r["display_name"], r.get("status"), r.get("can_backup", r.get("has_key"))) for r in rows)
        if signature != self.last_menu:
            self.last_menu = signature
            previous_menu = self.tray.contextMenu()
            menu = QMenu(self)
            menu.addAction(tr("Time Machine öffnen"), self.show_window)
            for row in rows:
                dest_menu = menu.addMenu(row["display_name"])
                name = row["name"]
                dest_menu.addAction(
                    tr("Jetzt sichern"), lambda checked=False, n=name: self.action("backup", name=n)
                )
                dest_menu.addAction(tr("Dateien wiederherstellen"), lambda checked=False, n=name: self.restore(n))
                dest_menu.addAction(
                    tr("Repository prüfen"), lambda checked=False, n=name: self.action("check", name=n)
                )
                dest_menu.addAction(tr("Abbrechen"), lambda checked=False, n=name: self.action("cancel", name=n))
            menu.addSeparator()
            menu.addAction(tr("Einstellungen"), self.settings)
            menu.addAction(tr("Beenden"), self.quit)
            self.tray.setContextMenu(menu)
            if previous_menu:
                previous_menu.deleteLater()

    def selected(self):
        index = self.list.currentRow()
        return self.rows[index]["name"] if 0 <= index < len(self.rows) else None

    def details(self, *_):
        name = self.selected()
        if not name:
            return
        row = next(r for r in self.rows if r["name"] == name)
        self.label.setText(row["display_name"])
        self.status_label.setText(status_text(row))
        self.info.setText(
            tr("Letzte erfolgreiche Sicherung: ")
            + date(row.get("last_success"))
            + tr("\nLetzte Prüfung: ")
            + date(row.get("last_check"))
            + tr("\nZeitplan: ")
            + (row.get("schedule") or tr("Nur auf Anfrage"))
            + (
                tr(" · aktiviert")
                if row.get("schedule_enabled")
                else tr(" · pausiert / noch nicht installiert")
                if row.get("schedule")
                else ""
            )
            + "\nSnapshots: "
            + str(row.get("snapshot_count", "–"))
            + tr("   ·   Gespeichert: ")
            + human_size(row.get("repository_bytes"))
            + "\n"
            + row["repository"]
        )
        running = row.get("status") == "running"
        progress = progress_view(row)
        self.progress.setVisible(progress["active"])
        self.progress_details.setVisible(progress["active"])
        self.progress_details.setText(progress["detail"] + "\n" + progress["speed"] + "\n" + progress["timing"])
        self.progress_details.setToolTip(progress["speed_hint"])
        percent = progress["percent"]
        if isinstance(percent, (int, float)):
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(max(0, min(1, percent)) * 1000))
            self.progress.setFormat(f"{percent * 100:.1f}%")
        else:
            self.progress.setRange(0, 0)
        error = (
            row.get("backup_error")
            if row.get("last_backup_status") == "failed"
            else row.get("error") or row.get("maintenance_error")
        )
        self.error_label.setText(translate_message(error or "")[-1500:])
        for btn in (
            self.backup_button,
            self.restore_button,
            self.check_button,
            self.dry_button,
            self.init_button,
        ):
            btn.setEnabled(not running and row.get("can_backup", row.get("has_key", False)))
        self.cancel_button.setEnabled(running)

    def action(self, command, extra=None, name=None):
        name = name or self.selected()
        if name:
            self.jobs.start([command, "--dest", name, "--json", *(extra or [])])

    def settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        if any(r.get("status") == "running" for r in self.rows):
            self.error(tr("Bitte laufende Vorgänge zuerst abschließen oder abbrechen."))
            return
        dialog = Settings(self)
        self.settings_dialog = dialog
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        def finished(result):
            self.settings_dialog = None
            if result == QDialog.DialogCode.Accepted:
                self.reload()
                self.jobs.start(["install"], self.timers_ready)
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.show()

    def restore(self, name=None):
        if isinstance(name, bool) or name is None:
            name = self.selected()
        if name:
            dialog = RestoreBrowser(self, name)
            self.dialogs.append(dialog)
            dialog.show()

    def logs(self):
        name = self.selected()
        if not name:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Protokoll · {p0}", p0=name))
        dialog.resize(850, 550)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self.engine.logs(name) or tr("Noch keine Protokolle vorhanden."))
        layout.addWidget(text)
        layout.addWidget(button(tr("Schließen"), dialog.close))
        bind_ui(dialog)
        dialog.exec()

    def key_menu(self, name=None):
        if isinstance(name, bool) or name is None:
            name = self.selected()
        if not name:
            return
        if self.key_dialog is not None:
            self.key_dialog.raise_()
            self.key_dialog.activateWindow()
            return
        if self.jobs.processes or any(r.get("status") == "running" for r in self.rows):
            self.error(tr("Bitte laufende Vorgänge zuerst abschließen oder abbrechen."))
            return
        dialog = KeyDialog(self, name)
        self.key_dialog = dialog
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        def finished(_):
            self.key_dialog = None
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def set_key(self):
        self.key_menu()

    def show_key(self):
        self.key_menu()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle(self):
        self.hide() if self.isVisible() else self.show_window()

    def quit(self):
        if self.jobs.processes:
            self.error(tr("Es laufen noch Vorgänge. Bitte zuerst abschließen oder abbrechen."))
            return
        QApplication.quit()

    def closeEvent(self, event):
        if self.native_panel or QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            self.quit()
            event.ignore()


def main(config_dir=None, state_dir=None):
    from .diagnostics import enable_diagnostics

    enable_diagnostics(state_dir)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("CachyOS Time Machine")
    app.setDesktopFileName(APP)
    app.setQuitOnLastWindowClosed(False)
    runtime = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation)
    lock = QLockFile(str(Path(runtime) / (APP + ".lock")))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Time Machine", tr("Time Machine läuft bereits im KDE-Systemabschnitt."))
        return 0
    try:
        window = Window(config_dir, state_dir)
    except (Error, OSError) as exc:
        QMessageBox.warning(None, tr("Konfiguration fehlerhaft"), str(exc))
        return 1
    if not QSystemTrayIcon.isSystemTrayAvailable() or "--tray" not in sys.argv:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
