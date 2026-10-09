import os
import shutil
import subprocess
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTime
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

from timemachine.core import atomic
from timemachine.gui import RestoreBrowser, Settings, Window
from timemachine.schedule import ScheduleEditor


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_jobs(app, window, timeout=15):
    deadline = time.monotonic() + timeout
    while window.jobs.processes and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not window.jobs.processes, "GUI worker failed to finish"


def test_settings_preserve_advanced_fields_and_add_dest(app, configured):
    engine, _, _ = configured
    engine.config["destinations"][0]["env"] = {"EXAMPLE": "preserved"}
    custom_schedule = "Mon..Fri *-*-* 07:30:00 Europe/Berlin"
    engine.config["destinations"][0]["schedule"] = custom_schedule
    atomic(engine.config_path, engine.config)
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    settings = Settings(window)
    settings.fields["display_name"].setText("USB Sicherung")
    settings.add_dest()
    settings.fields["repository"].setText("/another/repository")
    settings.schedule.frequency.setCurrentIndex(settings.schedule.frequency.findData("monthly"))
    settings.schedule.day.setValue(15)
    settings.schedule.time.setTime(QTime(18, 45))
    settings.destinations.setCurrentRow(0)
    assert settings.schedule.schedule() == custom_schedule
    settings.destinations.setCurrentRow(1)
    assert settings.schedule.schedule() == "*-*-15 18:45:00"
    settings.save()
    window.reload()
    assert not errors
    assert window.engine.config["destinations"][0]["display_name"] == "USB Sicherung"
    assert window.engine.config["destinations"][0]["env"] == {"EXAMPLE": "preserved"}
    assert len(window.engine.config["destinations"]) == 2
    assert window.engine.config["destinations"][0]["schedule"] == custom_schedule
    assert window.engine.config["destinations"][1]["schedule"] == "*-*-15 18:45:00"
    window.timer.stop()
    window.tray.hide()
    window.deleteLater()


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("manual", ""),
        ("hourly", "*-*-* *:20:00"),
        ("daily", "*-*-* 18:45:00"),
        ("weekly", "Thu *-*-* 18:45:00"),
        ("monthly", "*-*-15 18:45:00"),
        ("yearly", "*-06-15 18:45:00"),
    ],
)
def test_schedule_controls_generate_valid_systemd_calendars(app, mode, expected):
    editor = ScheduleEditor()
    editor.set_schedule("*-*-* 03:00:00")
    editor.frequency.setCurrentIndex(editor.frequency.findData(mode))
    editor.time.setTime(QTime(18, 45))
    editor.minute.setValue(20)
    editor.weekday.setCurrentIndex(3)
    editor.month.setCurrentIndex(5)
    editor.day.setValue(15)
    assert editor.schedule() == expected
    if expected:
        binary = shutil.which("systemd-analyze")
        assert binary, "systemd-analyze is required to validate generated calendars"
        result = subprocess.run([binary, "calendar", expected], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
    editor.deleteLater()


@pytest.mark.parametrize(
    "expression,mode",
    [
        ("daily", "daily"),
        ("weekly", "weekly"),
        ("monthly", "monthly"),
        ("yearly", "yearly"),
        ("*-*-* *:15:00", "hourly"),
        ("Sun *-*-* 12:30:00", "weekly"),
        ("*-02-29 09:00:00", "yearly"),
        ("*-*-31 09:00:00", "monthly"),
        ("Mon..Fri *-*-* 08:00:00 Europe/Berlin", "custom"),
        ("*-*-* 03:00:15", "custom"),
    ],
)
def test_existing_schedules_are_preserved_exactly(app, expression, mode):
    editor = ScheduleEditor()
    editor.set_schedule(expression)
    assert editor.frequency.currentData() == mode
    assert editor.schedule() == expression
    editor.deleteLater()


def test_file_picker_buttons_store_paths_and_cancel_without_changes(app, configured, tmp_path, monkeypatch):
    engine, source, _ = configured
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    settings = Settings(window)
    files = [str(tmp_path / "file with spaces.txt"), str(tmp_path / "üñïcode.txt")]
    folder = str(tmp_path / "selected folder")
    repository = str(tmp_path / "USB backup")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: (files, ""))
    choose_files = next(b for b in settings.findChildren(QPushButton) if b.text() == "Dateien auswählen …")
    choose_files.click()
    choose_files.click()
    assert settings.sources.toPlainText().splitlines() == [str(source), *files]
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: folder)
    next(b for b in settings.findChildren(QPushButton) if b.text() == "Ordner auswählen …").click()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: repository)
    settings.pick_repository()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([], ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: "")
    choose_files.click()
    settings.pick_repository()
    settings.save()
    window.reload()
    assert not errors
    assert window.engine.config["source"] == [str(source), *files, folder]
    assert window.engine.config["destinations"][0]["repository"] == repository
    window.timer.stop()
    window.tray.hide()
    window.deleteLater()


@pytest.mark.integration
def test_selected_exclusions_skip_literal_files_and_folder_descendants(app, rustic_engine, monkeypatch):
    engine, source, _ = rustic_engine
    excluded_file = source / "private[1]*.txt"
    excluded_file.write_text("secret")
    kept_file = source / "private1-other.txt"
    kept_file.write_text("keep")
    excluded_folder = source / "ignored [folder]!"
    excluded_folder.mkdir()
    (excluded_folder / "nested.txt").write_text("secret")
    atomic(engine.config_path, engine.config)
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    settings = Settings(window)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([str(excluded_file)], ""))
    settings.pick_paths(settings.excludes, excluded=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(excluded_folder))
    settings.pick_paths(settings.excludes, directory=True, excluded=True)
    settings.save()
    window.reload()
    assert not errors
    window.engine.backup("test")
    snapshot = window.engine.snapshots("test")[0]
    entries = window.engine.ls("test", snapshot["id"], str(source))
    assert {item["name"] for item in entries} == {"file.txt", "subdir", kept_file.name}
    window.timer.stop()
    window.tray.hide()
    window.deleteLater()


@pytest.mark.integration
def test_gui_restore_browser_process_and_filter(app, rustic_engine, tmp_path):
    engine, source, _ = rustic_engine
    engine.backup("test")
    atomic(engine.config_path, engine.config)
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    browser = RestoreBrowser(window, "test")
    wait_jobs(app, window)
    assert not errors
    assert browser.days.count() == 1
    assert browser.tree.topLevelItemCount() == 2
    browser.filter.setText("file.txt")
    visible = [
        browser.tree.topLevelItem(i)
        for i in range(browser.tree.topLevelItemCount())
        if not browser.tree.topLevelItem(i).isHidden()
    ]
    assert len(visible) == 1 and visible[0].text(0) == "file.txt"
    browser.up()
    wait_jobs(app, window)
    assert browser.path == str(source.parent)
    window.timer.stop()
    window.tray.hide()
    browser.deleteLater()
    window.deleteLater()
