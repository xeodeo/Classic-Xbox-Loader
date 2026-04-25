"""
ZIP extraction module with progress reporting via QThread.
"""
import os
import zipfile
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ExtractWorker(QThread):
    """Extracts a ZIP file in a background thread with progress signals."""
    progress = pyqtSignal(int, int)    # files_done, files_total
    file_progress = pyqtSignal(str)    # current filename
    finished = pyqtSignal(str)         # output directory path
    error = pyqtSignal(str)

    def __init__(self, zip_path: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.zip_path = zip_path
        self.output_dir = output_dir

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                members = zf.infolist()
                total = len(members)
                for i, member in enumerate(members, 1):
                    self.file_progress.emit(member.filename)
                    zf.extract(member, self.output_dir)
                    self.progress.emit(i, total)
            self.finished.emit(self.output_dir)
        except zipfile.BadZipFile:
            self.error.emit(f"Archivo ZIP corrupto: {self.zip_path}")
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            self.error.emit(str(e))


def find_iso_in_dir(directory: str):
    """Find the first .iso file in a directory tree. Returns path or None."""
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.lower().endswith('.iso'):
                return os.path.join(root, f)
    return None
