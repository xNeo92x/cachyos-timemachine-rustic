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
service_pid=
cleanup() {
  if [[ -n "$service_pid" ]]; then kill "$service_pid" 2>/dev/null || true; fi
  rm -rf "$task_dir"
}
trap cleanup EXIT
python install.py --no-panel --bin-dir "$task_dir/bin"
python -m timemachine.cli configure
python -m timemachine.cli service > "$task_dir/service.log" 2>&1 &
service_pid=$!
python -m timemachine.cli gui
set +e
timeout 20s plasmoidviewer -a "$PWD/plasma/org.cachyos.timemachine" > "$task_dir/plasma.log" 2>&1
result=$?
set -e
cat "$task_dir/service.log" "$task_dir/plasma.log"
[[ "$result" == 124 ]] # The applet must stay alive, rather than exit or crash.
if rg 'main.qml.*(Error|error|ReferenceError|TypeError|Cannot|Unable)|Type .* unavailable|Error loading applet' "$task_dir/plasma.log"; then
  exit 1
fi
