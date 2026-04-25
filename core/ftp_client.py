"""
FTP client for connecting to a modded Xbox console.
Key improvements over basic ftplib usage:
  - TCP keepalive prevents WinError 10053 on long transfers
  - CWD + relative STOR (not absolute path) — required by Xbox FTP servers
  - All operations serialized with RLock — safe to call from threads
  - Auto-reconnect + retry on connection drop during upload
  - Files uploaded before subdirs (avoids fragmentation, like iti.py)
"""
import os
import re
import socket
import ftplib
import threading
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

XBOX_PARTITIONS = ['C:', 'E:', 'F:', 'G:', 'X:', 'Y:', 'Z:']

# Maps server partition names (any case/format) to drive letters
# Covers: standard dashboards (e, E, e:, E:), PrometheOS (hdd0-e), EvoX, UnleashX
_PARTITION_MAP = {
    'c': 'C:', 'c:': 'C:', 'hdd0-c': 'C:',
    'e': 'E:', 'e:': 'E:', 'hdd0-e': 'E:',
    'f': 'F:', 'f:': 'F:', 'hdd0-f': 'F:',
    'g': 'G:', 'g:': 'G:', 'hdd0-g': 'G:',
    'x': 'X:', 'x:': 'X:', 'hdd0-x': 'X:',
    'y': 'Y:', 'y:': 'Y:', 'hdd0-y': 'Y:',
    'z': 'Z:', 'z:': 'Z:', 'hdd0-z': 'Z:',
}


def _apply_keepalive(sock):
    """Enable TCP keepalive on a socket to prevent idle-timeout disconnections."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Reduce keepalive interval so the Xbox doesn't drop the connection
        # during a large upload (Xbox FTP drops idle connections after ~2 min)
        if hasattr(socket, 'TCP_KEEPIDLE'):   # Linux
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        if hasattr(socket, 'TCP_KEEPINTVL'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        if hasattr(socket, 'TCP_KEEPCNT'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
    except Exception:
        pass


class FTPClient:
    """Wraps ftplib.FTP with Xbox-specific helpers.
    All operations are serialized with an RLock — safe to call from threads.
    """

    def __init__(self):
        self.ftp = None
        self.host = ''
        self.connected = False
        self._lock = threading.RLock()
        self._conn_params: tuple | None = None   # (host, port, user, pw, timeout)
        # Maps 'E:' -> '/E' (server path found at root)
        self._partition_paths: dict[str, str] = {}

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self, host: str, port: int = 21, user: str = 'xbox',
                password: str = 'xbox', timeout: int = 15) -> tuple:
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=timeout)
            ftp.login(user, password)
            ftp.encoding = 'utf-8'
            # Remove socket timeout after login so data transfers don't time out.
            # (The 15s timeout is only needed for the initial connect/login phase;
            # leaving it active causes WinError 10053 on slow Xbox transfers.)
            ftp.timeout = None
            ftp.sock.settimeout(None)
            # TCP keepalive on the control socket
            _apply_keepalive(ftp.sock)
            ftp.cwd('/')
            self.ftp = ftp
            self.host = host
            self._conn_params = (host, port, user, password, timeout)
            self.connected = True
            self._scan_partitions()
            logger.info(f"Connected to {host}. Partitions: {self._partition_paths}")
            return True, f"Conectado a {host}"
        except ftplib.error_perm as e:
            return False, f"Error de autenticacion: {e}"
        except OSError as e:
            return False, f"No se pudo conectar a {host}:{port} — {e}"
        except Exception as e:
            return False, str(e)

    def reconnect(self) -> bool:
        """Reconnect using the same credentials as the last connect() call."""
        if not self._conn_params:
            return False
        ok, msg = self.connect(*self._conn_params)
        if ok:
            logger.info("Reconnected successfully.")
        else:
            logger.warning(f"Reconnect failed: {msg}")
        return ok

    def _scan_partitions(self):
        """List '/' to discover which partition names this server uses."""
        self._partition_paths = {}
        try:
            lines = []
            self.ftp.retrlines('LIST', lines.append)
            for line in lines:
                parts = line.split(None, 8)
                if len(parts) < 2:
                    continue
                name = parts[-1].strip()
                drive = _PARTITION_MAP.get(name.lower())
                if drive and drive not in self._partition_paths:
                    self._partition_paths[drive] = '/' + name
        except Exception as e:
            logger.warning(f"Could not scan partitions: {e}")
        # Fallback if scan returned nothing
        if not self._partition_paths:
            for letter in 'cefgxyz':
                drive = letter.upper() + ':'
                self._partition_paths[drive] = '/' + letter

    def get_partition_path(self, drive: str) -> str:
        """Return the server path for a drive letter, e.g. 'E:' -> '/E'."""
        return self._partition_paths.get(drive, '/' + drive[0].lower())

    def disconnect(self):
        with self._lock:
            if self.ftp:
                try:
                    self.ftp.quit()
                except Exception:
                    pass
                self.ftp = None
            self.connected = False
            self._partition_paths = {}

    # ── Directory listing ─────────────────────────────────────────────────────

    def _parse_list_line(self, line: str, base: str) -> dict | None:
        """Parse one line of FTP LIST output (Unix or Windows/DOS format)."""
        line = line.strip()
        if not line:
            return None
        # Windows/DOS: "01-01-00  12:00AM       <DIR>          GAMES"
        if re.match(r'\d{2}-\d{2}-\d{2}', line) or '<DIR>' in line:
            is_dir = '<DIR>' in line
            parts  = line.split()
            name   = parts[-1]
            if name in ('.', '..'):
                return None
            try:
                size = 0 if is_dir else int(parts[-2])
            except (ValueError, IndexError):
                size = 0
            return {'name': name, 'size': size, 'is_dir': is_dir,
                    'path': base.rstrip('/') + '/' + name}
        # Unix: "drwxrwxrwx 1 ftp ftp 0 Jan  1 2000 GAMES"
        parts = line.split(None, 8)
        if len(parts) < 2:
            return None
        is_dir = line[0] == 'd'
        name   = parts[8].strip() if len(parts) >= 9 else parts[-1]
        if name in ('.', '..'):
            return None
        try:
            size = int(parts[4]) if len(parts) > 4 else 0
        except (ValueError, IndexError):
            size = 0
        return {'name': name, 'size': size, 'is_dir': is_dir,
                'path': base.rstrip('/') + '/' + name}

    def list_dir(self, path: str, silent: bool = False) -> list:
        """List a directory. path must be a server path e.g. '/E' or '/E/GAMES'."""
        with self._lock:
            if not self.ftp:
                return []
            try:
                self.ftp.cwd(path)
            except ftplib.error_perm as e:
                if not silent:
                    logger.error(f"FTP cwd error: {e}")
                return []
            except Exception as e:
                logger.error(f"FTP cwd fatal: {e}")
                self.connected = False
                self.ftp = None
                return []
            try:
                canon = self.ftp.pwd()
            except Exception:
                canon = path
            entries = []
            try:
                lines = []
                self.ftp.retrlines('LIST', lines.append)
                for line in lines:
                    entry = self._parse_list_line(line, canon)
                    if entry:
                        entries.append(entry)
            except Exception as e:
                logger.error(f"FTP list error: {e}")
            return entries

    # ── File operations ───────────────────────────────────────────────────────

    def upload_file(self, local_path: str, remote_path: str,
                    progress_callback=None) -> bool:
        """Upload a file using CWD + relative STOR (required by Xbox FTP servers).

        Xbox FTP servers (EvoX, UnleashX, XBMC4Xbox) do not support absolute
        paths in STOR. We must CWD to the target directory first, then issue
        STOR with just the filename — exactly as iti.py and FlashFXP do.
        """
        with self._lock:
            if not self.ftp:
                return False
            return self._do_upload(local_path, remote_path, progress_callback)

    def _do_upload(self, local_path: str, remote_path: str, progress_callback) -> bool:
        """Inner upload using CWD + relative STOR — matches iti.py approach.

        Xbox FTP servers (EvoX/UnleashX/XBMC) work reliably with relative STOR
        after an explicit CWD. Absolute-path STOR causes WinError 10053 on some
        Xbox/Windows combinations.
        """
        try:
            remote_path = remote_path.replace('\\', '/')
            remote_dir  = remote_path.rsplit('/', 1)[0] or '/'
            filename    = remote_path.rsplit('/', 1)[-1]

            file_size = os.path.getsize(local_path)
            uploaded  = [0]

            def cb(data):
                uploaded[0] += len(data)
                if progress_callback:
                    progress_callback(uploaded[0], file_size)

            self.ftp.cwd(remote_dir)
            with open(local_path, 'rb') as f:
                self.ftp.storbinary(f'STOR {filename}', f, callback=cb)
            return True
        except Exception as e:
            logger.error(f"Upload error [{remote_path}]: {e}")
            self.connected = False
            self.ftp = None
            return False

    def upload_file_with_retry(self, local_path: str, remote_path: str,
                               progress_callback=None) -> bool:
        """Upload with one automatic reconnect+retry on connection failure."""
        with self._lock:
            if not self.ftp:
                # Try reconnect before first attempt
                if not self.reconnect():
                    return False
            if self._do_upload(local_path, remote_path, progress_callback):
                return True
            # First attempt failed — reconnect and retry once
            logger.info("Upload failed, reconnecting and retrying...")
            if not self.reconnect():
                return False
            # Re-create the remote directory in case it was lost too
            remote_dir = remote_path.replace('\\', '/').rsplit('/', 1)[0]
            if remote_dir:
                self._make_dirs_unlocked(remote_dir)
            return self._do_upload(local_path, remote_path, progress_callback)

    def make_dirs(self, path: str):
        """Recursively create remote directories."""
        with self._lock:
            if not self.ftp:
                return
            self._make_dirs_unlocked(path)

    def _make_dirs_unlocked(self, path: str):
        """Create directories — must be called with self._lock held."""
        path = path.replace('\\', '/')
        parts = [p for p in path.split('/') if p]
        current = ''
        for part in parts:
            current = current + '/' + part
            try:
                self.ftp.mkd(current)
                logger.info(f"Created remote dir: {current}")
            except ftplib.error_perm:
                pass  # Directory already exists
            except Exception as e:
                logger.warning(f"mkd '{current}' unexpected error: {e}")

    def mkdir(self, path: str) -> tuple:
        with self._lock:
            try:
                self.ftp.mkd(path)
                return True, "Carpeta creada"
            except Exception as e:
                return False, str(e)

    def delete_file(self, path: str) -> tuple:
        with self._lock:
            try:
                self.ftp.delete(path)
                return True, "Archivo eliminado"
            except Exception as e:
                return False, str(e)

    def delete_dir(self, path: str) -> tuple:
        """Recursively delete a remote directory."""
        with self._lock:
            try:
                entries = self.list_dir(path)
                for e in entries:
                    if e['is_dir']:
                        self.delete_dir(e['path'])
                    else:
                        self.ftp.delete(e['path'])
                self.ftp.rmd(path)
                return True, "Carpeta eliminada"
            except Exception as e:
                return False, str(e)

    def rename(self, old_path: str, new_name: str) -> tuple:
        with self._lock:
            try:
                parent   = old_path.rsplit('/', 1)[0]
                new_path = parent + '/' + new_name
                self.ftp.rename(old_path, new_path)
                return True, "Renombrado"
            except Exception as e:
                return False, str(e)

    def download_file(self, remote_path: str, local_path: str,
                      progress_callback=None) -> tuple:
        with self._lock:
            try:
                size = 0
                try:
                    size = self.ftp.size(remote_path)
                except Exception:
                    pass
                downloaded = [0]
                os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
                with open(local_path, 'wb') as f:
                    def cb(data):
                        f.write(data)
                        downloaded[0] += len(data)
                        if progress_callback and size:
                            progress_callback(downloaded[0], size)
                    self.ftp.retrbinary(f'RETR {remote_path}', cb, blocksize=8192)
                return True, local_path
            except Exception as e:
                logger.error(f"FTP download error: {e}")
                return False, str(e)

    def detect_games_folder(self) -> str:
        """Scan common Xbox game folder paths and return the most likely one."""
        e_path = self._partition_paths.get('E:', '/e')
        f_path = self._partition_paths.get('F:', '/f')
        g_path = self._partition_paths.get('G:', '/g')
        # Only look for actual game folders — never TDATA/UDATA
        candidates = [
            f_path + '/GAMES', f_path + '/Games', f_path + '/games',
            e_path + '/GAMES', e_path + '/Games', e_path + '/games',
            g_path + '/GAMES', g_path + '/Games', g_path + '/games',
        ]
        best_path  = ''
        best_count = 0
        for path in candidates:
            entries = self.list_dir(path, silent=True)
            dirs = [e for e in entries if e['is_dir']]
            if len(dirs) > best_count:
                best_count = len(dirs)
                best_path  = path
        return best_path


# ── Upload worker ─────────────────────────────────────────────────────────────

class FTPUploadWorker(QThread):
    """Uploads an entire game folder to Xbox via FTP in the background.

    Matches iti.py approach exactly:
      - Acquires the FTP lock ONCE for the entire transfer (no interleaving)
      - Navigates to destination with a single absolute CWD
      - Uses only relative navigation inside (cwd(item) / cwd('..'))
      - Files uploaded before subdirectories (avoids HDD fragmentation)
      - STOR uses just the filename — never an absolute path
    """
    progress     = pyqtSignal(str, int, int)   # filename, bytes_done, file_total
    file_started = pyqtSignal(str)
    finished     = pyqtSignal()
    error        = pyqtSignal(str)

    def __init__(self, client: FTPClient, local_dir: str,
                 remote_dir: str, parent=None):
        super().__init__(parent)
        self.client     = client
        self.local_dir  = local_dir
        self.remote_dir = remote_dir
        self._cancelled = False

    def run(self):
        try:
            with self.client._lock:
                if not self.client.ftp:
                    raise Exception("No hay conexión FTP activa.")
                # Navigate to destination with ONE absolute CWD, then work relatively
                remote = self.remote_dir.replace('\\', '/').rstrip('/')
                parent    = remote.rsplit('/', 1)[0] or '/'
                game_name = remote.rsplit('/', 1)[-1]
                self.client.ftp.cwd(parent)
                try:
                    self.client.ftp.mkd(game_name)
                    logger.info(f"Created remote dir: {remote}")
                except ftplib.error_perm:
                    pass  # Already exists
                self.client.ftp.cwd(game_name)
                self._upload_dir(self.local_dir)
            if not self._cancelled:
                self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _upload_dir(self, local: str):
        """Upload contents of local dir to the current FTP directory.
        Must be called with self.client._lock held.
        Uses only relative FTP navigation — never absolute paths after the
        initial cwd() in run().  This matches iti.py exactly.
        """
        items = os.listdir(local)
        # Files first, then subdirectories (avoids HDD fragmentation on Xbox)
        files = sorted(i for i in items if os.path.isfile(os.path.join(local, i)))
        dirs  = sorted(i for i in items if os.path.isdir(os.path.join(local, i)))

        for item in files:
            if self._cancelled:
                return
            lp        = os.path.join(local, item)
            file_size = os.path.getsize(lp)
            uploaded  = [0]

            def cb(data, _fn=item, _sz=file_size):
                uploaded[0] += len(data)
                self.progress.emit(_fn, uploaded[0], _sz)

            self.file_started.emit(item)
            try:
                with open(lp, 'rb') as f:
                    self.client.ftp.storbinary(f'STOR {item}', f, callback=cb)
            except Exception as e:
                logger.error(f"Upload failed [{item}]: {e}")
                raise Exception(f"Error subiendo '{item}': {e}")

        for item in dirs:
            if self._cancelled:
                return
            lp = os.path.join(local, item)
            try:
                self.client.ftp.mkd(item)
            except ftplib.error_perm:
                pass  # Already exists
            self.client.ftp.cwd(item)
            self._upload_dir(lp)
            self.client.ftp.cwd('..')

    def cancel(self):
        self._cancelled = True


_ftp_client = FTPClient()


def get_client() -> FTPClient:
    return _ftp_client
