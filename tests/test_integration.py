"""Regression cases for migrating tray layouts without disturbing other widgets."""

import json

import pytest
from PySide6.QtQml import QJSEngine
from PySide6.QtWidgets import QApplication

from timemachine.integration import PLUGIN, panel_script


@pytest.mark.parametrize("legacy", [False, True])
def test_tray_migration_preserves_other_entries_and_is_idempotent(legacy):
    app = QApplication.instance() or QApplication([])
    engine = QJSEngine()
    setup = """
var messages = [];
function print(text) { messages.push(text); }
var values = {extraItems: ['volume', 'network'], shownItems: 'volume', hiddenItems: 'network,org.cachyos.timemachine', knownItems: ['volume', 'network']};
var tray = {
  currentConfigGroup: [],
  readConfig: function(key, fallback) { return values[key] === undefined ? fallback : values[key]; },
  writeConfig: function(key, value) { values[key] = value; },
  reloadConfig: function() {}
};
var removed = false;
var separate = {type: 'org.cachyos.timemachine', remove: function() { removed = true; }};
var wrapper = {
  type: 'org.kde.plasma.systemtray',
  readConfig: function(key, fallback) { return key === 'SystrayContainmentId' ? 42 : fallback; }
};
tray.type = 'org.kde.plasma.systemtray';
function desktopById(id) { if (id !== 42) throw Error('Wrong containment'); return tray; }
function panels() { return [{widgets: function() { return [separate, %s]; }}]; }
""" % ("wrapper" if legacy else "tray")
    assert not engine.evaluate(setup).isError()
    for _ in range(2):
        result = engine.evaluate(panel_script())
        assert not result.isError(), result.toString()
    values = json.loads(engine.evaluate("JSON.stringify(values)").toString())
    assert values["extraItems"] == ["volume", "network", PLUGIN]
    assert values["shownItems"] == ["volume", PLUGIN]
    assert values["hiddenItems"] == ["network"]
    assert values["knownItems"] == ["volume", "network", PLUGIN]
    assert engine.evaluate("removed").toBool()
    assert engine.evaluate("messages[1]").toString() == "CACHYOS_TRAY_OK"
    assert not engine.evaluate(panel_script(remove=True)).isError()
    values = json.loads(engine.evaluate("JSON.stringify(values)").toString())
    assert values["extraItems"] == ["volume", "network"]
    assert values["shownItems"] == ["volume"]
    assert values["hiddenItems"] == ["network"]
    assert values["knownItems"] == ["volume", "network"]
    app.processEvents()


def test_without_system_tray_retains_existing_panel_widget():
    app = QApplication.instance() or QApplication([])
    engine = QJSEngine()
    engine.evaluate("""
var message = '';
var removed = false;
function print(text) { message = text; }
function panels() { return [{widgets: function() { return [{type: 'org.cachyos.timemachine', remove: function() { removed = true; }}]; }}]; }
""")
    result = engine.evaluate(panel_script())
    assert not result.isError(), result.toString()
    assert not engine.evaluate("removed").toBool()
    assert engine.evaluate("message").toString() == "CACHYOS_TRAY_MISSING"
    app.processEvents()
