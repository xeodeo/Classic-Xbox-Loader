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
        CHUNK = 512 * 1024   # 512 KB read buffer
        EMIT_EVERY = 5 * 1024 * 1024  # emit progress at most every 5 MB
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                members = zf.infolist()
                total_bytes = sum(m.file_size for m in members) or 1
                done_bytes = 0
                last_emit = 0

                for member in members:
                    self.file_progress.emit(member.filename)

                    if member.is_dir():
                        zf.extract(member, self.output_dir)
                        continue

                    # ZIP spec uses '/' — build a proper OS path from parts
                    parts = [p for p in member.filename.split('/') if p and p != '..']
                    if not parts:
                        continue
                    dest = os.path.join(self.output_dir, *parts)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)

                    with zf.open(member) as src, open(dest, 'wb') as dst:
                        while True:
                            chunk = src.read(CHUNK)
                            if not chunk:
                                break
                            dst.write(chunk)
                            done_bytes += len(chunk)
                            if done_bytes - last_emit >= EMIT_EVERY:
                                last_emit = done_bytes
                                self.progress.emit(done_bytes, total_bytes)

            self.progress.emit(total_bytes, total_bytes)
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
