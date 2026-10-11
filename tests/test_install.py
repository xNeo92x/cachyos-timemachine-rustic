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
    assert (
        tmp_path / "data/plasma/plasmoids/org.cachyos.timemachine/contents/icons/cachyos-time-machine.svg"
    ).read_text() == (script.parent / "packaging/cachyos-time-machine.svg").read_text()
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
    assert "ab- und wieder anmelden" in result.stdout
    assert "Hidden=true" in (tmp_path / "config/autostart/cachyos-time-machine.desktop").read_text()


def rustic_helper_environment(tmp_path):
    tools = tmp_path / "helper-tools"
    tools.mkdir()
    # Force the helper's upgrade path without touching any host installation.
    stub = tools / "rustic"
    stub.write_text("#!/bin/sh\nprintf 'rustic 0.10.0\\n'\n")
    stub.chmod(0o755)
    env = dict(os.environ, PATH=str(tools) + ":" + os.environ.get("PATH", ""))
    script = Path(__file__).resolve().parent.parent / "packaging/install-rustic.sh"
    destination = tmp_path / "custom bin"
    destination.mkdir()
    return tools, env, script, destination


def test_rustic_helper_rejects_corrupt_download_without_replacing_binary(tmp_path):
    tools, env, script, destination = rustic_helper_environment(tmp_path)
    previous = destination / "rustic"
    previous.write_bytes(b"keep previous executable")
    curl = tools / "curl"
    curl.write_text("#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index('--output') + 1]).write_bytes(b'corrupt archive')\n")
    curl.chmod(0o755)
    result = subprocess.run(["bash", str(script), str(destination)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert previous.read_bytes() == b"keep previous executable"


def test_rustic_helper_retains_existing_supported_version(tmp_path):
    tools, env, script, destination = rustic_helper_environment(tmp_path)
    (tools / "rustic").write_text("#!/bin/sh\nprintf 'rustic 0.12.0\\n'\n")
    curl = tools / "curl"
    curl.write_text("#!/bin/sh\nexit 99\n")
    curl.chmod(0o755)
    result = subprocess.run(["bash", str(script), str(destination)], env=env, capture_output=True, text=True)
    assert result.returncode == 0 and "0.12.0" in result.stdout
    assert not (destination / "rustic").exists()


@pytest.mark.integration
def test_rustic_helper_installs_verified_release_into_path_with_spaces(tmp_path):
    archive = Path(os.environ.get("RUSTIC_TEST_ARCHIVE", "/tmp/rustic.tar.gz"))
    if not archive.is_file() or os.uname().machine != "x86_64":
        pytest.skip("The official x86_64 archive from CI's release download is required")
    tools, env, script, destination = rustic_helper_environment(tmp_path)
    # Reuse the actual upstream archive, avoiding a second network download.
    # The helper itself still performs its real SHA-256 check and extraction.
    env["TIMEMACHINE_TEST_ARCHIVE"] = str(archive)
    curl = tools / "curl"
    curl.write_text("#!/usr/bin/env python3\nimport os, sys, shutil\nassert sys.argv[-1] == 'https://github.com/rustic-rs/rustic/releases/download/v0.11.4/rustic-v0.11.4-x86_64-unknown-linux-gnu.tar.gz'\nshutil.copyfile(os.environ['TIMEMACHINE_TEST_ARCHIVE'], sys.argv[sys.argv.index('--output') + 1])\n")
    curl.chmod(0o755)
    result = subprocess.run(["bash", str(script), str(destination)], env=env, capture_output=True, text=True)
    assert result.returncode == 0 and "0.11.4" in result.stdout, result.stdout + result.stderr
    binary = destination / "rustic"
    assert binary.is_file() and os.access(binary, os.X_OK)
    assert subprocess.check_output([str(binary), "--version"], text=True).startswith("rustic v0.11.4")
