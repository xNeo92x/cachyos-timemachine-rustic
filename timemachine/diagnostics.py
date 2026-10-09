"""Private startup and native-crash diagnostics, including D-Bus activation."""

import faulthandler
import logging
import os
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import qVersion

from . import __version__
from .core import APP

_crash_file = None


def enable_diagnostics(state_dir=None):
    global _crash_file
    directory = Path(state_dir or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "desktop-service.log"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(fd, 0o600)
    _crash_file = os.fdopen(fd, "a", buffering=1)
    faulthandler.enable(file=_crash_file, all_threads=True)
    handler = logging.StreamHandler(_crash_file)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("timemachine")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("Starting version=%s Python=%s PySide=%s Qt=%s session=%s",
                __version__, sys.version.split()[0], pyside_version, qVersion(), os.environ.get("XDG_SESSION_TYPE", "unknown"))
    original_hook = sys.excepthook

    def exception_hook(kind, value, traceback):
        logger.error("Unhandled desktop exception", exc_info=(kind, value, traceback))
        original_hook(kind, value, traceback)

    sys.excepthook = exception_hook
