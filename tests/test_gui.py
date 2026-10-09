import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from timemachine.core import atomic
from timemachine.gui import RestoreBrowser, Settings, Window


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
    atomic(engine.config_path, engine.config)
    window = Window(engine.config_dir, engine.state_dir)
    errors = []
    window.error = errors.append
    settings = Settings(window)
    settings.fields["display_name"].setText("USB Sicherung")
    settings.add_dest()
    settings.fields["repository"].setText("/another/repository")
    settings.save()
    window.reload()
    assert not errors
    assert window.engine.config["destinations"][0]["display_name"] == "USB Sicherung"
    assert window.engine.config["destinations"][0]["env"] == {"EXAMPLE": "preserved"}
    assert len(window.engine.config["destinations"]) == 2
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
