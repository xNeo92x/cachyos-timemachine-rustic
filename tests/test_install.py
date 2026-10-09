import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_user_install_launcher_and_desktop_entries(tmp_path):
    binary = os.environ.get("RUSTIC_TEST_BINARY") or shutil.which("rustic")
    if not binary:
        pytest.skip("rustic binary required for installer test")
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    (bin_dir / "rustic").symlink_to(Path(binary).absolute())
    env = dict(os.environ)
    env.update(
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        XDG_DATA_HOME=str(tmp_path / "data"),
        XDG_STATE_HOME=str(tmp_path / "state"),
        PATH=str(bin_dir) + ":" + env.get("PATH", ""),
    )
    script = Path(__file__).resolve().parent.parent / "install.py"
    result = subprocess.run(
        [sys.executable, str(script), "--no-panel", "--bin-dir", str(tmp_path / "bin")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    launcher = tmp_path / "bin/cachyos-time-machine"
    assert launcher.is_file() and os.access(launcher, os.X_OK)
    result = subprocess.run(
        [str(launcher), "configure"], env=env, cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "config/cachyos-time-machine/config.json").exists()
    desktop = (tmp_path / "data/applications/cachyos-time-machine.desktop").read_text()
    autostart = (tmp_path / "config/autostart/cachyos-time-machine.desktop").read_text()
    assert str(launcher) in desktop
    assert " service" in autostart and "Hidden=false" in autostart
    assert (tmp_path / "data/plasma/plasmoids/org.cachyos.timemachine/contents/ui/main.qml").exists()
    assert str(launcher) in (tmp_path / "data/dbus-1/services/org.cachyos.TimeMachine.service").read_text()
    result = subprocess.run([str(launcher), "autostart", "disable"], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    result = subprocess.run(
        [sys.executable, str(script), "--no-panel", "--bin-dir", str(tmp_path / "bin")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Hidden=true" in (tmp_path / "config/autostart/cachyos-time-machine.desktop").read_text()
