"""Native Qt 6 desktop UI. QSystemTrayIcon becomes a KDE StatusNotifierItem."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QLockFile, QProcess, QStandardPaths, Qt, QTimer, QUrl
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
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
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


def human_size(value):
    if value is None:
        return "–"
    value = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def date(value):
    if not value:
        return "Noch nie"
    import datetime

    try:
        return (
            datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone()
            .strftime("%d.%m.%Y, %H:%M")
        )
    except ValueError:
        return value


def status_text(row):
    if row.get("status") == "running":
        return {
            "backup": "Sicherung läuft",
            "restore": "Wiederherstellung läuft",
            "check": "Repository wird geprüft",
            "retention": "Alte Sicherungen werden bereinigt",
            "init": "Repository wird eingerichtet",
            "dry-run": "Testlauf",
            "stats": "Statistik wird gelesen",
        }.get(row.get("phase"), "Vorgang läuft")
    if row.get("last_backup_status") == "failed":
        return "Letztes Backup fehlgeschlagen"
    if row.get("status") in ("failed", "interrupted"):
        return "Fehler / Vorgang unterbrochen"
    if row.get("maintenance_error"):
        return "Sicherung erfolgreich · Bereinigung fehlgeschlagen"
    if not row.get("has_key"):
        return "Einrichtung erforderlich"
    if row.get("stale"):
        return "Letzte Sicherung ist überfällig"
    return "Bereit" if not row.get("last_success") else "Deine Dateien sind gesichert"


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
                self.window.error(result.get("error", "Vorgang fehlgeschlagen."))
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
        self.setWindowTitle("Time Machine einrichten")
        self.resize(780, 700)
        self.config = json.loads(json.dumps(window.engine.config))
        self.index = None
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        basic = QWidget()
        form = QFormLayout(basic)
        self.sources = QPlainTextEdit()
        source = self.config.get("source", "~")
        self.sources.setPlainText("\n".join([source] if isinstance(source, str) else source))
        self.sources.setMaximumHeight(85)
        form.addRow("Quellen (ein Pfad pro Zeile)", self.sources)
        self.destinations = QListWidget()
        self.destinations.setMaximumHeight(95)
        form.addRow("Backup-Ziele", self.destinations)
        actions = QHBoxLayout()
        actions.addWidget(button("Ziel hinzufügen", self.add_dest, "list-add"))
        actions.addWidget(button("Ziel entfernen", self.remove_dest, "list-remove"))
        form.addRow(actions)
        self.fields = {}
        for key, title, hint in [
            ("name", "Interner Name", "z. B. nas"),
            ("display_name", "Anzeigename", "z. B. Synology NAS"),
            ("repository", "Repository", "/run/media/…/rustic oder opendal:sftp"),
            ("schedule", "Zeitplan", "*-*-* 03:00:00 · leer = nur manuell"),
            ("pre_command", "Vor Backup ausführen", "Optional: Laufwerk einhängen oder NAS wecken"),
            ("on_failure_command", "Bei Fehler ausführen", "Optionaler eigener Befehl"),
        ]:
            edit = QLineEdit()
            edit.setPlaceholderText(hint)
            form.addRow(title, edit)
            self.fields[key] = edit
        self.options = QPlainTextEdit()
        self.options.setMaximumHeight(105)
        form.addRow("Backend-Optionen (JSON)", self.options)
        note = QLabel(
            "NAS: opendal:sftp mit user, endpoint, root.\nCloud: opendal:s3 mit bucket, region, root. Zugangsdaten siehe README."
        )
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(basic, "Quellen & Ziele")
        policies = QWidget()
        pf = QFormLayout(policies)
        self.retention = {}
        for key, title in [
            ("daily", "Täglich behalten"),
            ("weekly", "Wöchentlich behalten"),
            ("monthly", "Monatlich behalten"),
            ("yearly", "Jährlich behalten"),
        ]:
            spin = QSpinBox()
            spin.setRange(0, 10000)
            spin.setValue(self.config.get("retention", RETENTION).get(key, 0))
            self.retention[key] = spin
            pf.addRow(title, spin)
        self.stale = QSpinBox()
        self.stale.setRange(1, 87600)
        self.stale.setValue(int(self.config.get("stale_hours", 48)))
        pf.addRow("Überfällig nach (Stunden)", self.stale)
        self.excludes = QPlainTextEdit()
        exclude = window.config_dir / self.config.get("exclude_file", "excludes.txt")
        self.excludes.setPlainText(exclude.read_text() if exclude.exists() else "")
        pf.addRow("Ausschlüsse (rustic-Globs)", self.excludes)
        pf.addRow(
            QLabel(
                "Beispiel: !.cache/   ·   !Downloads/   ·   !*.iso\n! schließt aus. Positive Muster schließen ein."
            )
        )
        tabs.addTab(policies, "Aufbewahrung & Ausschlüsse")
        advanced = QWidget()
        av = QVBoxLayout(advanced)
        av.addWidget(
            QLabel(
                "Weitere Optionen (env_file, password_command, Ziel-Aufbewahrung)\nkönnen direkt in config.json bearbeitet werden."
            )
        )
        av.addWidget(
            button(
                "config.json im Editor öffnen",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(window.engine.config_path))),
                "document-edit",
            )
        )
        av.addWidget(
            QLabel(
                "Danach diesen Dialog schließen und im Hauptfenster „Neu laden“ wählen.\nEigene Hook-Befehle werden als dein Benutzer ausgeführt."
            )
        )
        av.addStretch()
        tabs.addTab(advanced, "Erweitert")
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.destinations.currentRowChanged.connect(self.select_dest)
        self.rebuild()

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
                "Backend-Optionen sind kein gültiges JSON. Änderung wird beim Speichern erneut geprüft."
            )
        self.index = index if index >= 0 else None
        if self.index is None:
            return
        dest = self.config["destinations"][index]
        for key, edit in self.fields.items():
            edit.setText(dest.get(key, ""))
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
            self.window.error("Bitte zuerst Backend-Optionen korrigieren.")
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
        self.accept()


class RestoreBrowser(QDialog):
    def __init__(self, window, name):
        super().__init__(window)
        self.window, self.name = window, name
        self.path = "/"
        self.request = 0
        self.setWindowTitle("Dateien aus einer Sicherung wiederherstellen")
        self.resize(940, 640)
        layout = QVBoxLayout(self)
        heading = QLabel("Zurück zu deinen Dateien")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self.days = QComboBox()
        self.days.currentIndexChanged.connect(self.load_folder)
        layout.addWidget(self.days)
        navigation = QHBoxLayout()
        navigation.addWidget(button("Nach oben", self.up, "go-up"))
        navigation.addWidget(button("Wurzel", self.root, "go-home"))
        self.location = QLineEdit("/")
        self.location.returnPressed.connect(self.go_path)
        navigation.addWidget(self.location, 1)
        layout.addLayout(navigation)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Dateien filtern …")
        self.filter.textChanged.connect(self.filter_rows)
        layout.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Größe", "Geändert"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemActivated.connect(self.open_item)
        self.tree.installEventFilter(self)
        layout.addWidget(self.tree, 1)
        self.message = QLabel("Sicherungen werden gelesen …")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        self.restore_selected = button("Auswahl wiederherstellen", self.restore_item, "document-revert")
        self.restore_folder = button(
            "Diesen Ordner wiederherstellen", lambda: self.restore(self.path), "folder"
        )
        self.restore_selected.setEnabled(False)
        self.restore_folder.setEnabled(False)
        self.tree.itemSelectionChanged.connect(
            lambda: self.restore_selected.setEnabled(self.tree.currentItem() is not None)
        )
        actions.addWidget(self.restore_selected)
        actions.addWidget(self.restore_folder)
        actions.addStretch()
        actions.addWidget(button("Schließen", self.close))
        layout.addLayout(actions)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self.up)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.filter.setFocus)
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
            self.message.setText(result.get("error", "Sicherungen konnten nicht gelesen werden."))
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
            self.message.setText("Noch keine Sicherungen vorhanden.")

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
        self.message.setText("Verzeichnis wird gelesen …")

        def ready(result):
            if request != self.request:
                return
            if not result.get("ok"):
                self.message.setText(
                    result.get("error", "Verzeichnis konnte nicht gelesen werden.")
                    + "\nMit „Wurzel“ kannst du die Sicherung von oben durchsuchen."
                )
                return
            for node in result["entries"]:
                item = QTreeWidgetItem(
                    [
                        node["name"],
                        human_size(node.get("size")) if node["type"] != "dir" else "Ordner",
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
                f"{len(result['entries'])} Einträge · Wiederherstellung in einen neuen Ordner unter ~/Restored"
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
        self.message.setText("Wiederherstellung läuft. Fortschritt im Hauptfenster.")

        def ready(result):
            self.restore_folder.setEnabled(True)
            self.restore_selected.setEnabled(self.tree.currentItem() is not None)
            if result.get("ok"):
                self.message.setText("Wiederhergestellt: " + result["restored"])
                QDesktopServices.openUrl(QUrl.fromLocalFile(result["target"]))
            else:
                self.message.setText(result.get("error", "Wiederherstellung fehlgeschlagen."))

        self.window.jobs.start(
            ["restore", "--dest", self.name, "--snapshot", snapshot["id"], "--path", path, "--json"], ready
        )


class Window(QMainWindow):
    def __init__(self, config_dir=None, state_dir=None):
        super().__init__()
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
        layout.addWidget(QLabel("Deine Dateien. Jeder Tag. Ein sicherer Weg zurück."))
        tools = QHBoxLayout()
        tools.addWidget(button("Einstellungen", self.settings, "configure"))
        tools.addWidget(button("Neu laden", self.reload, "view-refresh"))
        tools.addWidget(
            button(
                "Zeitpläne aktivieren",
                lambda: self.jobs.start(["install"], self.timers_ready),
                "appointment-new",
            )
        )
        tools.addWidget(
            button(
                "Zeitpläne pausieren",
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
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("error")
        content.addWidget(self.error_label)
        content.addStretch()
        self.backup_button = button("Jetzt sichern", lambda: self.action("backup"), "document-save")
        self.restore_button = button("Dateien wiederherstellen", self.restore, "document-revert")
        content.addWidget(self.backup_button)
        content.addWidget(self.restore_button)
        actions = QHBoxLayout()
        self.check_button = button("Prüfen", lambda: self.action("check"), "checkmark")
        self.dry_button = button("Testlauf", lambda: self.action("backup", ["--dry-run"]), "system-run")
        self.cancel_button = button("Abbrechen", lambda: self.action("cancel"), "process-stop")
        actions.addWidget(self.check_button)
        actions.addWidget(self.dry_button)
        actions.addWidget(self.cancel_button)
        content.addLayout(actions)
        keys = QHBoxLayout()
        keys.addWidget(button("Schlüssel", self.key_menu, "dialog-password"))
        self.init_button = button("Repository initialisieren", lambda: self.action("init"), "folder-new")
        keys.addWidget(self.init_button)
        keys.addWidget(button("Protokoll", self.logs, "view-list-text"))
        content.addLayout(keys)
        split.addWidget(panel)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        footer = QLabel(f"Version {__version__} · Verschlüsselt und dedupliziert mit rustic")
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
        self.tray.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def error(self, text):
        QMessageBox.warning(self, "CachyOS Time Machine", text)

    def timers_ready(self, result):
        if result.get("ok"):
            QMessageBox.information(
                self, "Zeitpläne", "Zeitpläne aktiviert." if result.get("enabled") else "Zeitpläne pausiert."
            )
        else:
            self.error(result.get("error", "Zeitpläne konnten nicht angepasst werden."))

    def reload(self):
        try:
            self.engine = Engine(self.config_dir, self.state_dir)
            self.refresh()
        except (Error, OSError) as exc:
            self.error(str(exc))

    def refresh(self):
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
        configured = all(r.get("has_key") for r in rows)
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
        signature = tuple((r["name"], r["display_name"], r.get("status"), r.get("has_key")) for r in rows)
        if signature != self.last_menu:
            self.last_menu = signature
            previous_menu = self.tray.contextMenu()
            menu = QMenu(self)
            menu.addAction("Time Machine öffnen", self.show_window)
            for row in rows:
                dest_menu = menu.addMenu(row["display_name"])
                name = row["name"]
                dest_menu.addAction(
                    "Jetzt sichern", lambda checked=False, n=name: self.action("backup", name=n)
                )
                dest_menu.addAction("Dateien wiederherstellen", lambda checked=False, n=name: self.restore(n))
                dest_menu.addAction(
                    "Repository prüfen", lambda checked=False, n=name: self.action("check", name=n)
                )
                dest_menu.addAction("Abbrechen", lambda checked=False, n=name: self.action("cancel", name=n))
            menu.addSeparator()
            menu.addAction("Einstellungen", self.settings)
            menu.addAction("Beenden", self.quit)
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
            "Letzte erfolgreiche Sicherung: "
            + date(row.get("last_success"))
            + "\nLetzte Prüfung: "
            + date(row.get("last_check"))
            + "\nZeitplan: "
            + (row.get("schedule") or "Nur auf Anfrage")
            + (
                " · aktiviert"
                if row.get("schedule_enabled")
                else " · pausiert / noch nicht installiert"
                if row.get("schedule")
                else ""
            )
            + "\nSnapshots: "
            + str(row.get("snapshot_count", "–"))
            + "   ·   Gespeichert: "
            + human_size(row.get("repository_bytes"))
            + "\n"
            + row["repository"]
        )
        running = row.get("status") == "running"
        progress = row.get("progress", {})
        self.progress.setVisible(running)
        percent = progress.get("percent_done")
        if isinstance(percent, (int, float)):
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(max(0, min(1, percent)) * 1000))
            self.progress.setFormat(f"{percent * 100:.0f}% · {human_size(progress.get('bytes_done'))}")
        else:
            self.progress.setRange(0, 0)
        error = (
            row.get("backup_error")
            if row.get("last_backup_status") == "failed"
            else row.get("error") or row.get("maintenance_error")
        )
        self.error_label.setText((error or "")[-1500:])
        for btn in (
            self.backup_button,
            self.restore_button,
            self.check_button,
            self.dry_button,
            self.init_button,
        ):
            btn.setEnabled(not running and row.get("has_key", False))
        self.cancel_button.setEnabled(running)

    def action(self, command, extra=None, name=None):
        name = name or self.selected()
        if name:
            self.jobs.start([command, "--dest", name, "--json", *(extra or [])])

    def settings(self):
        if any(r.get("status") == "running" for r in self.rows):
            self.error("Bitte laufende Vorgänge zuerst abschließen oder abbrechen.")
            return
        dialog = Settings(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
            self.jobs.start(["install"], self.timers_ready)

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
        dialog.setWindowTitle("Protokoll · " + name)
        dialog.resize(850, 550)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self.engine.logs(name) or "Noch keine Protokolle vorhanden.")
        layout.addWidget(text)
        layout.addWidget(button("Schließen", dialog.close))
        dialog.exec()

    def key_menu(self):
        menu = QMenu(self)
        menu.addAction("Schlüssel speichern …", self.set_key)
        menu.addAction("Schlüssel anzeigen / extern sichern …", self.show_key)
        menu.addAction(
            "In 1Password sichern",
            lambda: self.jobs.start(["key", "save-1password", "--dest", self.selected()]),
        )
        menu.exec(self.cursor().pos())

    def set_key(self):
        name = self.selected()
        password, ok = QInputDialog.getText(
            self, "Backup-Schlüssel", "Neues Passwort (auch extern aufbewahren):", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        repeat, ok = QInputDialog.getText(
            self, "Backup-Schlüssel", "Passwort wiederholen:", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if password != repeat:
            self.error("Passwörter stimmen nicht überein.")
            return

        def ready(result):
            if result.get("ok"):
                QMessageBox.information(
                    self,
                    "Schlüssel gespeichert",
                    "Bitte bewahre das Passwort zusätzlich außerhalb dieses PCs auf.\nAls Nächstes: Repository initialisieren, dann Jetzt sichern.",
                )
            else:
                self.error(result.get("error", "Schlüssel konnte nicht gespeichert werden."))

        self.jobs.start(["key", "set", "--dest", name, "--stdin"], ready, password)

    def show_key(self):
        try:
            password = self.engine.show_key(self.selected())
        except Error as exc:
            self.error(str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Backup-Schlüssel extern sichern")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "In einem Passwortmanager oder auf Papier außerhalb dieses PCs sichern.\nOhne dieses Passwort sind die Backups nicht lesbar."
            )
        )
        value = QLineEdit(password)
        value.setReadOnly(True)
        value.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(value)
        layout.addWidget(button("Anzeigen", lambda: value.setEchoMode(QLineEdit.EchoMode.Normal)))
        layout.addWidget(button("Schließen", dialog.accept))
        dialog.exec()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle(self):
        self.hide() if self.isVisible() else self.show_window()

    def quit(self):
        if self.jobs.processes:
            self.error("Es laufen noch Vorgänge. Bitte zuerst abschließen oder abbrechen.")
            return
        QApplication.quit()

    def closeEvent(self, event):
        if QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            self.quit()
            event.ignore()


def main(config_dir=None, state_dir=None):
    app = QApplication([sys.argv[0]])
    app.setApplicationName("CachyOS Time Machine")
    app.setDesktopFileName(APP)
    app.setQuitOnLastWindowClosed(False)
    runtime = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation)
    lock = QLockFile(str(Path(runtime) / (APP + ".lock")))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Time Machine", "Time Machine läuft bereits im KDE-Systemabschnitt.")
        return 0
    try:
        window = Window(config_dir, state_dir)
    except (Error, OSError) as exc:
        QMessageBox.warning(None, "Konfiguration fehlerhaft", str(exc))
        return 1
    if not QSystemTrayIcon.isSystemTrayAvailable() or "--tray" not in sys.argv:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
