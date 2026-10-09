#!/bin/bash
# Native KDE choosers and the PySide parent both use real Wayland surfaces.
set -euo pipefail
task_dir=$(mktemp -d)
export XDG_RUNTIME_DIR="$task_dir/runtime"
export XDG_CONFIG_HOME="$task_dir/config"
export XDG_DATA_HOME="$task_dir/data"
export XDG_STATE_HOME="$task_dir/state"
export XDG_CACHE_HOME="$task_dir/cache"
mkdir -m 700 "$XDG_RUNTIME_DIR"
export WLR_BACKENDS=headless
export WLR_RENDERER=pixman
export WLR_LIBINPUT_NO_DEVICES=1
export QT_QPA_PLATFORM=wayland
export QT_QPA_PLATFORMTHEME=kde
export XDG_CURRENT_DESKTOP=KDE
export XDG_SESSION_TYPE=wayland
export LC_ALL=C.UTF-8
unset DISPLAY
cat > "$task_dir/sway.conf" <<'EOF'
xwayland disable
output HEADLESS-1 resolution 1280x1024
default_border normal
focus_on_window_activation focus
EOF
sway -c "$task_dir/sway.conf" > "$task_dir/sway.log" 2>&1 &
compositor_pid=$!
cleanup() {
  kill "$compositor_pid" || true
  cat "$task_dir/sway.log"
  rm -rf "$task_dir"
}
trap cleanup EXIT
python - <<'PY'
import os, time
from pathlib import Path
runtime = Path(os.environ['XDG_RUNTIME_DIR'])
deadline = time.monotonic() + 10
while not list(runtime.glob('wayland-*.lock')) or not list(runtime.glob('sway-ipc*.sock')):
    if time.monotonic() > deadline:
        raise SystemExit('Headless Wayland compositor did not start')
    time.sleep(0.05)
PY
export WAYLAND_DISPLAY
WAYLAND_DISPLAY=$(basename "$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'wayland-*' -print -quit)")
export SWAYSOCK
SWAYSOCK=$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'sway-ipc*.sock' -print -quit)
python tests/kde_picker_smoke.py
