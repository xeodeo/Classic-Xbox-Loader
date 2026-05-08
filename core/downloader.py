"""
Multi-threaded download module with resume support.
Splits downloads across NUM_THREADS parallel threads using Range headers.
"""
import os
import sys
import json
import time
import threading
import logging
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from core import config as _cfg

logger = logging.getLogger(__name__)

NUM_THREADS: int = _cfg.load().get('num_threads', 5)
CHUNK_SIZE = 65536  # 64 KB per read


class DownloadTask:
    """Represents a single download in the queue."""
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    ERROR = 'error'
    CANCELLED = 'cancelled'

    def __init__(self, url: str, output_path: str, game_name: str, session: requests.Session):
        self.url = url
        self.output_path = output_path
        self.game_name = game_name
        self.session = session
        self.status = self.PENDING
        self.bytes_done = 0
        self.total_bytes = 0
        self.speed = 0.0
        self.error_msg = ''
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially


class DownloadWorker(QThread):
    """QThread that performs multi-threaded or single-threaded download."""
    progress = pyqtSignal(int, int)       # bytes_done, total_bytes
    speed_update = pyqtSignal(float)       # bytes/sec
    status_changed = pyqtSignal(str)
    finished = pyqtSignal(str)             # output path on success
    error = pyqtSignal(str)

    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self.task = task

    def run(self):
        task = self.task
        task.status = DownloadTask.DOWNLOADING
        self.status_changed.emit(task.status)
        try:
            os.makedirs(os.path.dirname(task.output_path), exist_ok=True)

            head = task.session.head(task.url, allow_redirects=True, timeout=30)
            task.total_bytes = int(head.headers.get('Content-Length', 0))
            accepts_ranges = head.headers.get('Accept-Ranges', 'none').lower() != 'none'

            if accepts_ranges and task.total_bytes > 0 and NUM_THREADS > 1:
                self._download_multipart(task)
            else:
                self._download_single(task)

            if not task._cancel_event.is_set():
                task.status = DownloadTask.COMPLETED
                self.status_changed.emit(task.status)
                self.finished.emit(task.output_path)

        except Exception as e:
            if not task._cancel_event.is_set():
                task.status = DownloadTask.ERROR
                task.error_msg = str(e)
                self.status_changed.emit(task.status)
                self.error.emit(str(e))
            logger.error(f"Download error for {task.game_name}: {e}")

    def _emit_progress(self, task, lock, speed_window, t_now):
        """Emit progress and current speed using a sliding 4-second window."""
        speed_window.append((t_now, task.bytes_done))
        # keep only last 4 seconds
        cutoff = t_now - 4.0
        while len(speed_window) > 2 and speed_window[0][0] < cutoff:
            speed_window.pop(0)
        if len(speed_window) >= 2:
            dt = speed_window[-1][0] - speed_window[0][0]
            db = speed_window[-1][1] - speed_window[0][1]
            task.speed = db / dt if dt > 0 else 0.0
        self.progress.emit(task.bytes_done, task.total_bytes)
        self.speed_update.emit(task.speed)

    def _download_multipart(self, task: DownloadTask):
        total = task.total_bytes
        chunk_size = total // NUM_THREADS
        ranges = [
            (i * chunk_size, (i + 1) * chunk_size - 1 if i < NUM_THREADS - 1 else total - 1)
            for i in range(NUM_THREADS)
        ]
        temp_files = [f"{task.output_path}.part{i}" for i in range(NUM_THREADS)]
        lock = threading.Lock()
        errors = []
        speed_window = []

        def download_chunk(idx, start, end, temp_path):
            MAX_RETRIES = 5
            for attempt in range(MAX_RETRIES):
                if task._cancel_event.is_set():
                    return
                try:
                    # Resume from however far we got (including previous attempts)
                    existing = 0
                    mode = 'wb'
                    if os.path.exists(temp_path):
                        existing = os.path.getsize(temp_path)
                        if existing >= (end - start + 1):
                            if attempt == 0:
                                with lock:
                                    task.bytes_done += existing
                            return
                        mode = 'ab'

                    cur_start = start + existing
                    if attempt == 0 and existing > 0:
                        with lock:
                            task.bytes_done += existing

                    resp = task.session.get(
                        task.url,
                        headers={'Range': f'bytes={cur_start}-{end}'},
                        stream=True, timeout=90
                    )
                    ct = resp.headers.get('Content-Type', '')
                    if 'text/html' in ct:
                        resp.close()
                        with lock:
                            errors.append(
                                "El servidor devolvió HTML en lugar del archivo.\n"
                                "Inicia sesión en Internet Archive (pestaña Configuración) para descargar."
                            )
                        return

                    expected = end - cur_start + 1
                    received = 0
                    with open(temp_path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                            if task._cancel_event.is_set():
                                return
                            task._pause_event.wait()
                            f.write(chunk)
                            received += len(chunk)
                            with lock:
                                task.bytes_done += len(chunk)
                                self._emit_progress(task, lock, speed_window, time.time())

                    if received >= expected:
                        return  # chunk complete
                    # Connection dropped early — retry after brief wait
                    wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                    logger.warning(f"Chunk {idx}: recibidos {received}/{expected} bytes, reintento {attempt+1}/{MAX_RETRIES} en {wait}s")
                    time.sleep(wait)

                except Exception as e:
                    wait = 2 ** attempt
                    logger.warning(f"Chunk {idx} error (intento {attempt+1}/{MAX_RETRIES}): {e} — reintentando en {wait}s")
                    time.sleep(wait)

            # All retries exhausted
            with lock:
                errors.append(f"Chunk {idx}: falló después de {MAX_RETRIES} intentos.")

        threads = [
            threading.Thread(target=download_chunk, args=(i, s, e, temp_files[i]), daemon=True)
            for i, (s, e) in enumerate(ranges)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            # Clean up temp files on error
            for tp in temp_files:
                try:
                    os.remove(tp)
                except OSError:
                    pass
            raise Exception(f"Descarga fallida: {'; '.join(errors)}")
        if task._cancel_event.is_set():
            return

        # Merge temp files into final output
        with open(task.output_path, 'wb') as out:
            for temp_path in temp_files:
                if os.path.exists(temp_path):
                    with open(temp_path, 'rb') as inp:
                        while True:
                            buf = inp.read(CHUNK_SIZE * 16)
                            if not buf:
                                break
                            out.write(buf)
                    os.remove(temp_path)

        # Validate final file size
        actual = os.path.getsize(task.output_path)
        if task.total_bytes > 0 and actual < task.total_bytes:
            os.remove(task.output_path)
            raise Exception(
                f"Archivo incompleto: se descargaron {actual:,} bytes de {task.total_bytes:,} esperados. "
                "Intenta de nuevo — Internet Archive puede haber cortado la conexión."
            )

    def _download_single(self, task: DownloadTask):
        existing = 0
        mode = 'wb'
        headers = {}
        if os.path.exists(task.output_path):
            existing = os.path.getsize(task.output_path)
            if existing > 0:
                headers['Range'] = f'bytes={existing}-'
                mode = 'ab'
                task.bytes_done = existing

        resp = task.session.get(task.url, headers=headers, stream=True, timeout=90)
        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            resp.close()
            raise Exception(
                "El servidor devolvió HTML en lugar del archivo.\n"
                "Inicia sesión en Internet Archive (pestaña Configuración) para descargar."
            )
        if task.total_bytes == 0:
            task.total_bytes = int(resp.headers.get('Content-Length', 0)) + existing

        speed_window = []
        with open(task.output_path, mode) as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if task._cancel_event.is_set():
                    return
                task._pause_event.wait()
                f.write(chunk)
                task.bytes_done += len(chunk)
                now = time.time()
                speed_window.append((now, task.bytes_done))
                cutoff = now - 4.0
                while len(speed_window) > 2 and speed_window[0][0] < cutoff:
                    speed_window.pop(0)
                if len(speed_window) >= 2:
                    dt = speed_window[-1][0] - speed_window[0][0]
                    db = speed_window[-1][1] - speed_window[0][1]
                    task.speed = db / dt if dt > 0 else 0.0
                self.progress.emit(task.bytes_done, task.total_bytes)
                self.speed_update.emit(task.speed)

        # Validate final file size
        if task.total_bytes > 0 and task.bytes_done < task.total_bytes:
            raise Exception(
                f"Archivo incompleto: se descargaron {task.bytes_done:,} bytes de {task.total_bytes:,} esperados. "
                "Intenta de nuevo — Internet Archive puede haber cortado la conexión."
            )

    def cancel(self):
        self.task._cancel_event.set()
        self.task._pause_event.set()

    def pause(self):
        self.task._pause_event.clear()
        self.task.status = DownloadTask.PAUSED

    def resume(self):
        self.task._pause_event.set()
        self.task.status = DownloadTask.DOWNLOADING


def _history_file() -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    return os.path.join(base, 'downloads_history.json')


class DownloadManager:
    """Global download queue and worker manager."""

    def __init__(self):
        self.queue: list = []
        self.workers: dict = {}
        self._listeners: list = []
        self._load_history()

    def _save_history(self):
        terminal = (DownloadTask.COMPLETED, DownloadTask.ERROR, DownloadTask.CANCELLED)
        data = [
            {
                'game_name': t.game_name,
                'url': t.url,
                'output_path': t.output_path,
                'total_bytes': t.total_bytes,
                'status': t.status,
                'error_msg': t.error_msg,
            }
            for t in self.queue if t.status in terminal
        ]
        try:
            with open(_history_file(), 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Could not save downloads history: {e}")

    def _load_history(self):
        try:
            path = _history_file()
            if not os.path.exists(path):
                return
            with open(path, encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                return
            for item in json.loads(content):
                task = DownloadTask(
                    item.get('url', ''),
                    item['output_path'],
                    item['game_name'],
                    None,
                )
                task.total_bytes = item.get('total_bytes', 0)
                task.bytes_done = task.total_bytes
                task.status = item.get('status', DownloadTask.COMPLETED)
                task.error_msg = item.get('error_msg', '')
                self.queue.append(task)
        except Exception as e:
            logger.warning(f"Could not load downloads history: {e}")

    def add_download(self, url: str, output_path: str, game_name: str,
                     session: requests.Session) -> DownloadTask:
        for task in self.queue:
            if task.output_path == output_path:
                return task
        task = DownloadTask(url, output_path, game_name, session)
        self.queue.append(task)
        self._notify()
        return task

    def start(self, task: DownloadTask) -> DownloadWorker:
        worker = DownloadWorker(task)
        self.workers[task.output_path] = worker
        worker.finished.connect(lambda _: self._save_history())
        worker.error.connect(lambda _: self._save_history())
        worker.start()
        self._notify()
        return worker

    def cancel(self, task: DownloadTask):
        w = self.workers.get(task.output_path)
        if w:
            w.cancel()
        task.status = DownloadTask.CANCELLED
        self._notify()
        self._save_history()

    def pause(self, task: DownloadTask):
        w = self.workers.get(task.output_path)
        if w:
            w.pause()
        self._notify()

    def resume(self, task: DownloadTask):
        w = self.workers.get(task.output_path)
        if w:
            w.resume()
        self._notify()

    def remove(self, task: DownloadTask):
        """Remove a finished/cancelled task from the queue (does not delete files)."""
        if task in self.queue:
            self.queue.remove(task)
        self.workers.pop(task.output_path, None)
        self._save_history()
        self._notify()

    def remove_with_file(self, task: DownloadTask):
        """Remove task from queue and delete its output file from disk."""
        self.remove(task)
        try:
            if task.output_path and os.path.exists(task.output_path):
                os.remove(task.output_path)
        except Exception as e:
            logger.warning(f"Could not delete file {task.output_path}: {e}")

    def add_listener(self, fn):
        self._listeners.append(fn)

    def _notify(self):
        for fn in self._listeners:
            try:
                fn()
            except Exception:
                pass


_manager = DownloadManager()


def get_manager() -> DownloadManager:
    return _manager
