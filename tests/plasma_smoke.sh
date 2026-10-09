#!/bin/bash
# Run in a disposable D-Bus session with native Plasma 6 packages.
set -euo pipefail
task_dir=$(mktemp -d)
export XDG_CONFIG_HOME="$task_dir/config"
export XDG_DATA_HOME="$task_dir/data"
export XDG_STATE_HOME="$task_dir/state"
export XDG_CACHE_HOME="$task_dir/cache"
export QT_QPA_PLATFORM=offscreen
export QT_QUICK_BACKEND=software
cleanup() {
  python - <<'PY'
from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusMessage
app = QCoreApplication([])
QDBusConnection.sessionBus().call(QDBusMessage.createMethodCall('org.cachyos.TimeMachine', '/TimeMachine', 'org.cachyos.TimeMachine', 'Shutdown'))
PY
  rm -rf "$task_dir"
}
trap cleanup EXIT
python install.py --no-panel --bin-dir "$task_dir/bin"
python -m timemachine.cli configure
# No manually pre-started service: reproduces the user's immediate post-install launch.
python -m timemachine.cli gui
cp -r plasma/org.cachyos.timemachine "$task_dir/applet"
# Test-only readiness markers: a live viewer alone does not prove the applet loaded.
python - "$task_dir/applet/contents/ui/main.qml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text().replace('id: root', 'id: root\n    Component.onCompleted: console.info("TIMEMACHINE_APPLET_READY")', 1)
text = text.replace('serviceError = "";', 'serviceError = ""; console.info("TIMEMACHINE_STATUS_READY");', 1)
probe = Path('tests/plasma_tray_probe.qml').read_text()
text = text.replace('import QtQuick\n', 'import QtQuick\nimport QtTest\n', 1)
text = text.replace('id: root', 'id: root\n' + probe, 1)
p.write_text(text)
# The system tray is an embedded containment, not a top-level desktop.
# Current Plasma embeds its QML in the native plugin; configure the viewer's
# first containment (id 1) and tray (id 2), without replacing any KDE code.
import os
installed = Path(os.environ['XDG_DATA_HOME']) / 'plasma/plasmoids/org.cachyos.timemachine/contents/ui/main.qml'
installed.write_text(text)
config = Path(os.environ['XDG_CONFIG_HOME']) / 'plasmoidviewer-appletsrc'
config.write_text('''[Containments][1][Applets][2][General]
extraItems=org.cachyos.timemachine
shownItems=org.cachyos.timemachine
knownItems=org.cachyos.timemachine
''')
PY
set +e
timeout 35s plasmoidviewer -a org.kde.plasma.systemtray -f horizontal -l bottomedge -s 800x80 > "$task_dir/plasma.log" 2>&1
result=$?
set -e
cat "$task_dir/plasma.log"
[[ "$result" == 124 ]] # The applet must stay alive, rather than exit or crash.
for marker in APPLET TRAY POPUP STATUS ICON CLICK CLOSE ACTIVATE; do
  rg "TIMEMACHINE_${marker}_READY" "$task_dir/plasma.log"
done
if rg "TIMEMACHINE_TEST_FAILED|file://$task_dir/(applet|data/plasma/plasmoids/org.cachyos.timemachine)/contents/ui/main.qml:[0-9]+|Type .* unavailable|Error loading applet" "$task_dir/plasma.log"; then
  exit 1
fi
