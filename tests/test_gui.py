import json
import os
import shutil
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTime
from PySide6.QtWidgets import QApplication, QPushButton

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


@pytest.fixture
def chooser(tmp_path, monkeypatch):
    """A real child process implementing KDE's output/cancel/crash protocol."""
    import timemachine.filepicker as module

    response = tmp_path / "response.json"
    arguments = tmp_path / "arguments.json"
    helper = tmp_path / "kdialog"
    helper.write_text("#!" + sys.executable + "\n" +
                      "import json, os, resource, signal, sys, time\n" +
                      f"response = json.load(open({str(response)!r}))\n" +
                      f"json.dump(sys.argv[1:], open({str(arguments)!r}, 'w'))\n" +
                      "resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n" +
                      "if response.get('crash'): os.kill(os.getpid(), signal.SIGSEGV)\n" +
                      "time.sleep(response.get('delay', 0))\n" +
                      "sys.stdout.write(response.get('output', ''))\n" +
                      "sys.exit(response.get('code', 0))\n")
    helper.chmod(0o755)
    original_which = module.shutil.which
    monkeypatch.setattr(module.shutil, "which", lambda name: str(helper) if name == "kdialog" else original_which(name))

    def configure(paths=(), code=0, crash=False, delay=0):
        response.write_text(json.dumps({"output": "\n".join(paths) + ("\n" if paths else ""),
                                        "code": code, "crash": crash, "delay": delay}))

    configure.arguments = arguments
    configure.helper = helper
    configure()
    return configure


def wait_picker(app, settings):
    deadline = time.monotonic() + 5
    while settings.file_picker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert settings.file_picker is None, "Picker process did not finish"


def test_file_picker_buttons_store_paths_and_cancel_without_changes(app, configured, tmp_path, chooser):
    engine, source, _ = configured
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    settings = Settings(window)
    settings.show()
    files = [str(tmp_path / "file with spaces.txt"), str(tmp_path / "üñïcode.txt")]
    folder = str(tmp_path / "selected folder")
    repository = str(tmp_path / "USB backup")
    chooser(files)
    choose_files = next(b for b in settings.findChildren(QPushButton) if b.text() == "Dateien auswählen …")
    choose_files.click()
    wait_picker(app, settings)
    choose_files.click()
    wait_picker(app, settings)
    assert settings.sources.toPlainText().splitlines() == [str(source), *files]
    args = json.loads(chooser.arguments.read_text())
    assert "--multiple" in args and "--separate-output" in args and "--getopenfilename" in args
    chooser([folder])
    settings.pick_paths(settings.sources, directory=True)
    wait_picker(app, settings)
    chooser([repository])
    settings.pick_repository()
    wait_picker(app, settings)
    assert settings.isVisible() and settings.isEnabled()
    chooser(code=1)
    choose_files.click()
    wait_picker(app, settings)
    settings.pick_repository()
    wait_picker(app, settings)
    settings.save()
    window.reload()
    assert not errors
    assert window.engine.config["source"] == [str(source), *files, folder]
    assert window.engine.config["destinations"][0]["repository"] == repository
    window.timer.stop()
    window.tray.hide()
    window.deleteLater()


def test_nas_picker_opens_network_and_preserves_remote_url(app, configured, chooser):
    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    settings = Settings(window)
    chooser(["smb://neo:private-password@nas.local/NAS/CachyOS Backup/"])
    settings.show()
    next(b for b in settings.findChildren(QPushButton) if b.text() == "NAS / Netzwerk …").click()
    wait_picker(app, settings)
    args = json.loads(chooser.arguments.read_text())
    assert args[args.index("--getexistingdirectory") + 1] == "smb://"
    assert "--attach" not in args  # Wayland must not receive an X11 window ID.
    assert settings.isVisible()
    assert engine.dest("test")["repository"] != settings.fields["repository"].text()
    assert settings.fields["repository"].text() == "smb://neo@nas.local/NAS/CachyOS%20Backup"
    chooser(code=1)
    settings.pick_repository()
    wait_picker(app, settings)
    assert settings.isVisible()
    settings.save()
    window.reload()
    assert not errors
    assert window.engine.dest("test")["repository"] == "smb://neo@nas.local/NAS/CachyOS%20Backup"
    assert "private-password" not in engine.config_path.read_text()
    window.timer.stop()
    window.tray.hide()
    window.deleteLater()


def test_settings_and_picker_acceptance_are_independent(app, configured, tmp_path, monkeypatch, chooser):
    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    jobs = []
    monkeypatch.setattr(window.jobs, "start", lambda *args: jobs.append(args))
    window.settings()
    settings = window.settings_dialog
    window.settings()
    assert window.settings_dialog is settings
    repository = str(tmp_path / "chosen backup")
    chooser([repository])
    settings.pick_repository()
    picker = settings.file_picker
    settings.pick_repository()
    assert settings.file_picker is picker
    wait_picker(app, settings)
    assert window.settings_dialog is settings and settings.isVisible()
    assert not jobs
    assert engine.dest("test")["repository"] != repository
    settings.save()
    assert window.settings_dialog is None
    assert window.engine.dest("test")["repository"] == repository
    assert len(jobs) == 1
    window.settings()
    assert window.settings_dialog.fields["repository"].text() == repository
    window.settings_dialog.reject()
    assert len(jobs) == 1
    window.timer.stop()
    window.deleteLater()


@pytest.mark.parametrize("selection", ["nas", "sources", "exclusions"])
def test_native_picker_crash_keeps_unsaved_settings_and_allows_retry(app, configured, chooser, selection):
    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    errors = []
    window.error = errors.append
    window.settings()
    settings = window.settings_dialog
    settings.fields["display_name"].setText("Unsaved NAS name")
    original = engine.config_path.read_text()
    sources = settings.sources.toPlainText()
    repository = settings.fields["repository"].text()
    exclusions = settings.excludes.toPlainText()
    choose = (lambda: settings.pick_repository(network=True)) if selection == "nas" else (
        lambda: settings.pick_paths(settings.sources if selection == "sources" else settings.excludes,
                                    excluded=selection == "exclusions"))
    chooser(crash=True)
    choose()
    wait_picker(app, settings)
    assert len(errors) == 1 and "unerwartet beendet" in errors[0]
    assert window.settings_dialog is settings and settings.isVisible() and settings.isEnabled()
    assert settings.fields["display_name"].text() == "Unsaved NAS name"
    assert settings.sources.toPlainText() == sources
    assert settings.fields["repository"].text() == repository
    assert settings.excludes.toPlainText() == exclusions
    assert engine.config_path.read_text() == original
    chooser(code=1)
    choose()
    wait_picker(app, settings)
    assert len(errors) == 1
    settings.reject()
    window.timer.stop()
    window.deleteLater()


@pytest.mark.parametrize("missing", [False, True])
def test_picker_missing_or_unlaunchable_preserves_settings(app, configured, chooser, monkeypatch, missing):
    import timemachine.filepicker as module

    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    errors = []
    window.error = errors.append
    window.settings()
    settings = window.settings_dialog
    chooser.helper.unlink()
    if missing:
        monkeypatch.setattr(module.shutil, "which", lambda name: None)
    settings.pick_repository(network=True)
    wait_picker(app, settings)
    assert len(errors) == 1
    assert settings.isVisible() and settings.isEnabled()
    settings.reject()
    window.timer.stop()
    window.deleteLater()


def test_close_settings_cancels_child_without_late_widget_callback(app, configured, chooser):
    engine, _, _ = configured
    window = Window(engine.config_dir, engine.state_dir, native_panel=True)
    errors = []
    window.error = errors.append
    window.settings()
    settings = window.settings_dialog
    chooser(delay=30)
    settings.pick_repository()
    picker = settings.file_picker
    settings.reject()
    assert window.settings_dialog is None
    wait_picker(app, settings)
    assert picker.cancelled
    assert not errors
    window.timer.stop()
    window.deleteLater()


@pytest.mark.integration
def test_selected_exclusions_skip_literal_files_and_folder_descendants(app, rustic_engine, chooser):
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
    chooser([str(excluded_file)])
    settings.pick_paths(settings.excludes, excluded=True)
    wait_picker(app, settings)
    chooser([str(excluded_folder)])
    settings.pick_paths(settings.excludes, directory=True, excluded=True)
    wait_picker(app, settings)
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
