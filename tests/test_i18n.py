"""Language selection must not change backup configuration or editable values."""

import ast
import json
import os
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton, QTabWidget

from timemachine.core import Engine, Error, atomic, validate
from timemachine.filepicker import FilePicker
from timemachine.gui import RestoreBrowser, Window, status_text
from timemachine.i18n import EN, configure, language, system_language, tr
from timemachine.service import Bridge


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("env,expected", [
    ({"LANG": "de_DE.UTF-8"}, "de"),
    ({"LANG": "de_AT.UTF-8"}, "de"),
    ({"LANG": "en_GB.UTF-8"}, "en"),
    ({"LANG": "fr_FR.UTF-8"}, "en"),
    ({"LANG": "de_DE.UTF-8", "LANGUAGE": "en:de"}, "en"),
    ({"LANG": "en_US.UTF-8", "LANGUAGE": "de:en"}, "de"),
    ({"LANG": "en_US.UTF-8", "LANGUAGE": "fr:de:en"}, "de"),
    ({"LANG": "en_US.UTF-8", "LC_MESSAGES": "de_DE.UTF-8"}, "de"),
    ({"LANG": "de_DE.UTF-8", "LC_ALL": "en_US.UTF-8"}, "en"),
    ({"LANG": "de_DE.UTF-8", "LC_ALL": "C", "LANGUAGE": "de"}, "en"),
])
def test_system_locale_and_kde_preferences(env, expected):
    assert system_language(env) == expected


def test_catalog_preserves_template_arguments_and_covers_calls():
    root = Path(__file__).resolve().parent.parent
    for path in (root / "timemachine").glob("*.py"):
        if path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                assert isinstance(node.args[0], ast.Constant)
                assert node.args[0].value in EN, (path.name, node.args[0].value)
    qml = (root / "plasma/org.cachyos.timemachine/contents/ui/main.qml").read_text()
    for literal in re.findall(r'root\.tr\(("(?:[^"\\]|\\.)*")\)', qml):
        assert json.loads(literal) in EN
    for source, translated in EN.items():
        assert set(re.findall(r"\{p\d+\}", source)) == set(re.findall(r"\{p\d+\}", translated))
    configure("en")
    assert tr("Backup-Quelle fehlt: {p0}", p0="/home/Schließen/{name}") == "Backup source is missing: /home/Schließen/{name}"


def test_invalid_language_is_rejected(configured):
    engine, _, _ = configured
    engine.config["language"] = "fr"
    with pytest.raises(Error, match="language"):
        validate(engine.config)


def test_saved_language_updates_qt_and_plasma_and_preserves_user_data(app, configured, monkeypatch):
    engine, source, _ = configured
    schedule = "Mon..Fri *-*-* 07:30:00 Europe/Berlin"
    engine.dest("test").update(display_name="Schließen", schedule=schedule)
    atomic(engine.config_path, engine.config)
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    monkeypatch.setattr(window.jobs, "start", lambda *args: None)
    bridge = Bridge(window)
    assert window.backup_button.text() == "Jetzt sichern"
    window.settings()
    settings = window.settings_dialog
    assert settings.language.currentData() == "system"
    settings.language.setCurrentIndex(settings.language.findData("en"))
    settings.save()
    assert window.settings_dialog is None
    assert window.backup_button.text() == "Back up now"
    assert window.label.text() == "Schließen"  # A user's display name is not translated.
    assert window.engine.config["language"] == "en"
    assert window.engine.dest("test")["schedule"] == schedule
    assert window.engine.config["source"] == [str(source)]
    status = json.loads(bridge.Status())
    assert status["language"] == "en"
    assert status["translations"]["Einstellungen"] == "Settings"
    assert status["destinations"][0]["status_text"] == "Ready"
    assert status["destinations"][0]["last_success_text"] == "Never"
    window.settings()
    settings = window.settings_dialog
    assert settings.windowTitle() == "Set up Time Machine"
    assert settings.language.currentData() == "en"
    assert settings.schedule.frequency.itemText(settings.schedule.frequency.findData("daily")) == "Daily"
    assert settings.schedule.weekday.itemText(0) == "Monday"
    assert settings.schedule.month.itemText(0) == "January"
    assert settings.findChild(QTabWidget).tabText(1) == "Retention & exclusions"
    assert settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).text() == "Save"
    settings.language.setCurrentIndex(settings.language.findData("de"))
    settings.save()
    assert window.backup_button.text() == "Jetzt sichern"
    assert json.loads(bridge.Status())["language"] == "de"
    assert window.engine.dest("test")["schedule"] == schedule
    window.settings()
    settings = window.settings_dialog
    settings.language.setCurrentIndex(settings.language.findData("system"))
    monkeypatch.setenv("LANGUAGE", "en")
    settings.save()
    assert window.backup_button.text() == "Back up now"
    assert Engine(engine.config_dir, engine.state_dir).config["language"] == "system"
    assert language() == "en"
    window.timer.stop()
    window.deleteLater()
    app.processEvents()


def test_english_password_restore_and_backend_errors(app, configured, monkeypatch):
    engine, _, _ = configured
    engine.config["language"] = "en"
    atomic(engine.config_path, engine.config)
    engine.password_path(engine.dest("test")).unlink()
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    monkeypatch.setattr(window.jobs, "start", lambda *args: None)
    window.key_menu("test")
    key = window.key_dialog
    assert key.windowTitle() == "Backup password · test"
    assert key.save_button.text() == "Save password"
    key.password.setText("Speichern")
    key.repeat.setText("different")
    key.save_password()
    assert key.message.text() == "Passwords do not match."
    assert key.password.text() == "Speichern"
    key.reject()
    restore = RestoreBrowser(window, "test")
    assert restore.windowTitle() == "Restore files from a backup"
    assert restore.tree.headerItem().text(1) == "Size"
    assert restore.filter.placeholderText() == "Filter files …"
    assert any(btn.text() == "Restore selection" for btn in restore.findChildren(QPushButton))
    with pytest.raises(Error, match="Unknown backup destination"):
        window.engine.dest("missing")
    assert status_text({"status": "running", "phase": "backup"}) == "Backing up"
    restore.deleteLater()
    window.timer.stop()
    window.deleteLater()
    app.processEvents()


def test_native_picker_inherits_selected_language(app, monkeypatch):
    configure("en")
    monkeypatch.setenv("LANGUAGE", "de")
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setattr("timemachine.filepicker.shutil.which", lambda _: "/usr/bin/kdialog")
    picker = FilePicker()
    calls = []
    monkeypatch.setattr(picker.process, "start", lambda *args: calls.append(args))
    picker.start("Choose folder", os.path.expanduser("~"), directory=True)
    env = picker.process.processEnvironment()
    assert env.value("LANGUAGE") == "en"
    assert env.value("LC_MESSAGES") == "en_US.UTF-8"
    assert not env.contains("LC_ALL")
    assert calls[0][1][1] == "Choose folder"
    picker.deleteLater()
