#!/bin/bash
# Run in a disposable D-Bus session with native Plasma 6 packages.
set -euo pipefail
task_dir=$(mktemp -d)
export XDG_CONFIG_HOME="$task_dir/config"
export XDG_DATA_HOME="$task_dir/data"
export XDG_STATE_HOME="$task_dir/state"
export XDG_CACHE_HOME="$task_dir/cache"
export QT_QPA_PLATFORM=xcb
export QT_QUICK_BACKEND=software
# The disposable Arch container has no configured /etc/localtime. Give rustic
# a known zone, as a configured desktop session would have.
export TZ=UTC
export TIMEMACHINE_TEST_LANGUAGE="${1:-en}"
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
python - <<'PYSETUP'
import os
from pathlib import Path
from timemachine.core import atomic
base = Path(os.environ['XDG_STATE_HOME']).parent
source = base / 'source'
source.mkdir()
(source / 'file.txt').write_text('Passwordless Plasma backup')
# Keep a real backup alive across several one-second popup refreshes even on
# fast CI hosts. Source bytes are unique; progress output is never substituted.
for index in range(16):
    (source / f'large-{index}.bin').write_bytes(os.urandom(32 * 1024 ** 2))
wrapper = base / 'rustic-one-cpu'
wrapper.write_text('''#!/usr/bin/python
import os, sys
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
os.execvp('rustic', ['rustic', *sys.argv[1:]])
''')
wrapper.chmod(0o700)
atomic(Path(os.environ['XDG_CONFIG_HOME']) / 'cachyos-time-machine/config.json', {
    'language': os.environ['TIMEMACHINE_TEST_LANGUAGE'],
    'rustic_binary': str(wrapper),
    'source': str(source), 'destinations': [{'name': 'test', 'repository': str(base / 'repo')}],
})
PYSETUP
# No manually pre-started service: reproduces the user's immediate post-install launch.
python -m timemachine.cli gui
# Exercise production dialog lifetimes with KDE's actual native helper, not a mocked picker.
QT_QPA_PLATFORMTHEME=kde XDG_CURRENT_DESKTOP=KDE python tests/kde_picker_smoke.py
cp -r plasma/org.cachyos.timemachine "$task_dir/applet"
# Test-only readiness markers: a live viewer alone does not prove the applet loaded.
python - "$task_dir/applet/contents/ui/main.qml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text().replace('id: root', 'id: root\n    Component.onCompleted: console.info("TIMEMACHINE_APPLET_READY")', 1)
text = text.replace('serviceError = "";', 'serviceError = ""; console.info("TIMEMACHINE_STATUS_READY");', 1)
import json, os
probe = Path('tests/plasma_tray_probe.qml').read_text().replace('property string expectedLanguage: "en"',
    'property string expectedLanguage: ' + json.dumps(os.environ['TIMEMACHINE_TEST_LANGUAGE']))
text = text.replace('import QtQuick\n', 'import QtQuick\nimport QtTest\n', 1)
text = text.replace('id: root', 'id: root\n' + probe, 1)
p.write_text(text)
# Run a real Plasma shell with one panel and its embedded native tray.
# No SDK ViewerCorona or replacement of KDE's compiled QML is involved.
import os
installed = Path(os.environ['XDG_DATA_HOME']) / 'plasma/plasmoids/org.cachyos.timemachine/contents/ui/main.qml'
installed.write_text(text)
config = Path(os.environ['XDG_CONFIG_HOME']) / 'plasma-org.kde.plasma.desktop-appletsrc'
config.write_text('''[Containments][1]
plugin=org.kde.panel
formfactor=2
location=4
lastScreen=0

[Containments][1][Applets][2]
plugin=org.kde.plasma.systemtray

[Containments][1][Applets][2][General]
extraItems=org.cachyos.timemachine
shownItems=org.cachyos.timemachine
knownItems=org.cachyos.timemachine
''')
PY
set +e
timeout 45s plasmashell --no-respawn > "$task_dir/plasma.log" 2>&1
result=$?
set -e
cat "$task_dir/plasma.log"
python -m timemachine.cli log --dest test
[[ "$result" == 124 ]] # The shell must stay alive, rather than exit or crash.
for marker in APPLET TRAY POPUP STATUS ICON CLICK CLOSE ACTIVATE LOCALIZED_UI LIVE_PROGRESS COMPACT_LAYOUT NAS_METRICS_LAYOUT PASSWORDLESS_BACKUP ACTION_MENU KEY_DIALOG; do
  rg "TIMEMACHINE_${marker}_READY" "$task_dir/plasma.log"
done
if rg "TIMEMACHINE_TEST_FAILED|file://$task_dir/(applet|data/plasma/plasmoids/org.cachyos.timemachine)/contents/ui/main.qml:[0-9]+|Type .* unavailable|Error loading applet" "$task_dir/plasma.log"; then
  exit 1
fi
