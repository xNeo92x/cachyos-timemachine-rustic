import os
import signal
import stat
import subprocess
import sys

from timemachine import __version__


def test_native_crash_is_logged_even_without_terminal(tmp_path):
    code = """
import os, resource, signal
from timemachine.diagnostics import enable_diagnostics
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
enable_diagnostics(os.environ['TEST_STATE_DIR'])
os.kill(os.getpid(), signal.SIGSEGV)
"""
    result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, TEST_STATE_DIR=str(tmp_path)),
                            capture_output=True, text=True)
    assert result.returncode == -signal.SIGSEGV
    path = tmp_path / "desktop-service.log"
    text = path.read_text()
    assert "version=" + __version__ in text
    assert "PySide=" in text and "Qt=" in text
    assert "Fatal Python error: Segmentation fault" in text
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
