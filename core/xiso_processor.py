"""
Wrapper for extract-xiso.exe to process Xbox ISO files.
Usage: extract-xiso.exe -x <iso_path>
The tool extracts the ISO contents to a folder named after the ISO (without extension).
"""
import os
import sys
import subprocess
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


def get_app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def get_xiso_path() -> str:
    return os.path.join(get_app_dir(), 'extract iso a xiso', 'extract-xiso.exe')


class XisoWorker(QThread):
    """Runs extract-xiso.exe in a background thread, streaming its output."""
    output_line = pyqtSignal(str)   # stdout line
    finished = pyqtSignal(str)      # extracted folder path
    error = pyqtSignal(str)

    def __init__(self, iso_path: str, parent=None):
        super().__init__(parent)
        self.iso_path = iso_path

    def run(self):
        xiso_exe = get_xiso_path()
        if not os.path.exists(xiso_exe):
            self.error.emit(f"No se encontro extract-xiso.exe en:\n{xiso_exe}")
            return
        if not os.path.exists(self.iso_path):
            self.error.emit(f"ISO no encontrada: {self.iso_path}")
            return

        work_dir = os.path.dirname(self.iso_path)
        try:
            proc = subprocess.Popen(
                [xiso_exe, '-x', self.iso_path],
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            for line in proc.stdout:
                self.output_line.emit(line.rstrip())
            proc.wait()

            if proc.returncode != 0:
                self.error.emit(f"extract-xiso.exe termino con codigo {proc.returncode}")
                return

            iso_name = os.path.splitext(os.path.basename(self.iso_path))[0]
            extracted_dir = os.path.join(work_dir, iso_name)
            self.finished.emit(extracted_dir if os.path.isdir(extracted_dir) else work_dir)

        except Exception as e:
            logger.error(f"xiso error: {e}")
            self.error.emit(str(e))
