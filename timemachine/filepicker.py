"""Run native KDE choosers outside the PySide service (also on Wayland)."""

import logging
import shutil

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtWidgets import QApplication


class FilePicker(QObject):
    completed = Signal(object, str)

    def __init__(self):
        # The application owns this object until the child exits. Closing Settings
        # must never destroy a running QProcess or call back into deleted widgets.
        super().__init__(QApplication.instance())
        self.process = QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.cancelled = False
        self.done = False
        self.directory = False

    def start(self, title, start, directory=False):
        self.directory = directory
        binary = shutil.which("kdialog")
        if not binary:
            self.finish([], "Für die KDE-Dateiauswahl bitte installieren: sudo pacman -S kdialog")
            return
        args = ["--title", title]
        if directory:
            args += ["--getexistingdirectory", start]
        else:
            args += ["--multiple", "--separate-output", "--getopenfilename", start]
        # No nested Qt event loop, shell, or X11-only foreign parent handle.
        self.process.start(binary, args)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.finish([], "Die KDE-Dateiauswahl konnte nicht gestartet werden. Bitte kdialog prüfen.")

    def finished(self, code, status):
        if self.cancelled:
            self.finish([], "")
        elif status == QProcess.ExitStatus.CrashExit or code not in (0, 1):
            logging.getLogger("timemachine").error("kdialog failed: exit=%s status=%s", code, status.name)
            self.finish([], "Die KDE-Dateiauswahl wurde unerwartet beendet. Deine Eingaben bleiben erhalten.")
        elif code == 1:
            self.finish([], "")  # KDE uses 1 for the user's Cancel button.
        else:
            try:
                text = bytes(self.process.readAllStandardOutput()).decode("utf-8").removesuffix("\n")
                paths = ([text] if self.directory else text.split("\n")) if text else []
                if self.directory and ("\n" in text or "\r" in text):
                    raise ValueError("multiline path")
                self.finish(paths, "")
            except (UnicodeError, ValueError):
                self.finish([], "Die Dateiauswahl hat einen ungültigen Pfad zurückgegeben.")

    def finish(self, paths, error):
        if self.done:
            return
        self.done = True
        self.completed.emit(paths, error)
        self.deleteLater()

    def cancel(self):
        self.cancelled = True
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            QTimer.singleShot(1000, self, self.kill_if_running)

    def kill_if_running(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
