"""
Installation panel - Extract ZIP, process with extract-xiso, install to Xbox.
Features:
  - Auto-detect games folder already on Xbox
  - Per-file progress bar + general progress bar during FTP upload
"""
import os
import json
import ftplib
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QGroupBox,
    QComboBox, QSplitter, QProgressBar, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from core.extractor import ExtractWorker, find_iso_in_dir
from core.xiso_processor import XisoWorker
from core.ftp_client import get_client, FTPUploadWorker


def _sanitize_fatx_name(name: str) -> str:
    """Remove characters not supported by Xbox FATX filesystem: ( ) ,"""
    import re
    name = re.sub(r'[(),]', '', name)
    name = re.sub(r' +', ' ', name).strip()
    return name


def _fmt(b: int) -> str:
    if b < 1024 ** 2:
        return f"{b/1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"


def _count_local(path: str) -> tuple[int, int]:
    """Return (file_count, total_bytes) for a directory tree."""
    files, size = 0, 0
    for root, _, fnames in os.walk(path):
        for f in fnames:
            files += 1
            try:
                size += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return files, size


class DetectDestWorker(QThread):
    result = pyqtSignal(str)   # server path or ''
    def run(self):
        self.result.emit(get_client().detect_games_folder())


class SmartUploadWorker(FTPUploadWorker):
    """Extends FTPUploadWorker with per-file progress, overall progress,
    and automatic reconnect+retry on connection drops.

    On any upload failure the worker:
      1. Reconnects the FTP client.
      2. Re-navigates to the exact remote directory it was in.
      3. Retries the file upload up to MAX_RETRIES times.
    """
    file_progress    = pyqtSignal(str, int, int)      # filename, bytes_done, file_total
    overall_progress = pyqtSignal(int, int, int, int)  # files_done, total_files, bytes_done, total_bytes

    MAX_RETRIES = 3

    def __init__(self, client, local_dir, remote_dir, parent=None):
        super().__init__(client, local_dir, remote_dir, parent)
        self._total_files    = 0
        self._total_bytes    = 0
        self._done_files     = 0
        self._done_bytes     = 0
        self._current_remote = ''   # Absolute remote path we're currently in

    def run(self):
        self._total_files, self._total_bytes = _count_local(self.local_dir)
        self._done_files = 0
        self._done_bytes = 0
        try:
            with self.client._lock:
                if not self.client.ftp:
                    raise Exception("No hay conexión FTP activa.")
                remote    = self.remote_dir.replace('\\', '/').rstrip('/')
                parent    = remote.rsplit('/', 1)[0] or '/'
                game_name = remote.rsplit('/', 1)[-1]
                self.client.ftp.cwd(parent)
                try:
                    self.client.ftp.mkd(game_name)
                except ftplib.error_perm:
                    pass
                self.client.ftp.cwd(game_name)
                self._current_remote = remote
                self._upload_dir(self.local_dir)
            if not self._cancelled:
                self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _reconnect_and_navigate(self):
        """Reconnect FTP and CWD back to the directory we were in."""
        if not self.client.reconnect():
            raise Exception("No se pudo reconectar al Xbox.")
        self.client.ftp.cwd(self._current_remote)

    def _upload_file_with_retry(self, local_path: str, filename: str, file_size: int):
        """Upload a single file with automatic reconnect+retry on failure."""
        bytes_before = self._done_bytes
        last_err = None

        for attempt in range(self.MAX_RETRIES):
            if self._cancelled:
                return
            if attempt > 0:
                self.file_started.emit(f"↩ Reintento {attempt}/{self.MAX_RETRIES - 1}: {filename}")
                self._reconnect_and_navigate()

            uploaded = [0]

            def _cb(data, _fn=filename, _fb=bytes_before, _fs=file_size):
                uploaded[0] += len(data)
                self.file_progress.emit(_fn, uploaded[0], _fs or 1)
                self.overall_progress.emit(
                    self._done_files, self._total_files,
                    _fb + uploaded[0], self._total_bytes
                )

            try:
                with open(local_path, 'rb') as f:
                    self.client.ftp.storbinary(f'STOR {filename}', f, callback=_cb)
                # Success
                self._done_files += 1
                self._done_bytes += file_size
                self.overall_progress.emit(
                    self._done_files, self._total_files,
                    self._done_bytes, self._total_bytes
                )
                return
            except Exception as e:
                last_err = e
                self.client.connected = False
                self.client.ftp = None

        raise Exception(
            f"Error subiendo '{filename}' tras {self.MAX_RETRIES} intentos: {last_err}"
        )

    def _upload_dir(self, local: str):
        items = os.listdir(local)
        files = sorted(i for i in items if os.path.isfile(os.path.join(local, i)))
        dirs  = sorted(i for i in items if os.path.isdir(os.path.join(local, i)))

        for item in files:
            if self._cancelled:
                return
            lp        = os.path.join(local, item)
            file_size = 0
            try:
                file_size = os.path.getsize(lp)
            except OSError:
                pass
            self.file_started.emit(item)
            self._upload_file_with_retry(lp, item, file_size)

        for item in dirs:
            if self._cancelled:
                return
            lp = os.path.join(local, item)
            try:
                self.client.ftp.mkd(item)
            except ftplib.error_perm:
                pass
            self.client.ftp.cwd(item)
            self._current_remote += '/' + item
            self._upload_dir(lp)
            self.client.ftp.cwd('..')
            self._current_remote = self._current_remote.rsplit('/', 1)[0]


class InstallPanel(QWidget):
    def __init__(self, downloads_dir, parent=None):
        super().__init__(parent)
        self.downloads_dir     = downloads_dir
        self._state_file       = os.path.join(downloads_dir, '.processed.json')
        self._extract_worker   = None
        self._xiso_worker      = None
        self._upload_worker    = None
        self._detect_worker    = None
        self._extracting_zip   = None   # ZIP currently being extracted
        self._processing_iso   = None   # ISO currently being processed by xiso
        self._current_zip      = None
        self._current_iso      = None
        self._current_game_dir = None
        self._detected_dest    = ''
        self._processed        = self._load_state()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("Instalación de Juegos")
        hf = QFont('Segoe UI', 18)
        hf.setBold(True)
        header.setFont(hf)
        layout.addWidget(header)

        sub = QLabel("Pipeline: Extraer ZIP  →  Procesar ISO  →  Transferir al Xbox")
        sub.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        layout.addWidget(sub)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: file list ───────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        lbl = QLabel("ARCHIVOS DESCARGADOS (ZIP)")
        lbl.setStyleSheet("color: #9e9e9e; font-size: 11px; font-weight: 600;")
        ll.addWidget(lbl)
        self.files_list = QListWidget()
        self.files_list.currentItemChanged.connect(self._on_file_selected)
        ll.addWidget(self.files_list, 1)
        ref_btn = QPushButton("🔄  Actualizar lista")
        ref_btn.clicked.connect(self._refresh_files)
        ll.addWidget(ref_btn)
        splitter.addWidget(left)

        # ── Right: pipeline + progress ────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.setSpacing(12)

        self.selected_label = QLabel("Selecciona un archivo de la lista")
        self.selected_label.setStyleSheet("color: #9e9e9e; font-size: 12px; font-style: italic;")
        rl.addWidget(self.selected_label)

        # ── Pipeline group ────────────────────────────────────────────────────
        pipe = QGroupBox("Pipeline de instalación")
        pl = QVBoxLayout(pipe)
        pl.setSpacing(12)

        # Step 1 — Extract ZIP
        s1 = QHBoxLayout()
        self.s1_st = QLabel("⬜")
        s1.addWidget(self.s1_st)
        s1.addWidget(QLabel("1. Extraer ZIP"))
        s1.addStretch()
        self.btn_extract = QPushButton("Extraer ZIP")
        self.btn_extract.setEnabled(False)
        self.btn_extract.clicked.connect(self._do_extract)
        s1.addWidget(self.btn_extract)
        pl.addLayout(s1)

        self.extract_bar = QProgressBar()
        self.extract_bar.setMaximum(100)
        self.extract_bar.setVisible(False)
        self.extract_bar.setFixedHeight(8)
        self.extract_bar.setTextVisible(False)
        pl.addWidget(self.extract_bar)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background: #2a2a2a;")
        sep1.setFixedHeight(1)
        pl.addWidget(sep1)

        # Step 2 — extract-xiso
        s2 = QHBoxLayout()
        self.s2_st = QLabel("⬜")
        s2.addWidget(self.s2_st)
        s2.addWidget(QLabel("2. Procesar con extract-xiso"))
        s2.addStretch()
        self.btn_xiso = QPushButton("Procesar ISO")
        self.btn_xiso.setEnabled(False)
        self.btn_xiso.clicked.connect(self._do_xiso)
        s2.addWidget(self.btn_xiso)
        pl.addLayout(s2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background: #2a2a2a;")
        sep2.setFixedHeight(1)
        pl.addWidget(sep2)

        # Step 3 — FTP install
        s3_top = QHBoxLayout()
        self.s3_st = QLabel("⬜")
        s3_top.addWidget(self.s3_st)
        s3_top.addWidget(QLabel("3. Instalar en Xbox (FTP)"))
        s3_top.addStretch()

        # Detect destination button
        self.detect_dest_btn = QPushButton("🔍 Detectar destino")
        self.detect_dest_btn.setMinimumHeight(30)
        self.detect_dest_btn.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #ccc; border: 1px solid #3a3a3a; border-radius: 5px; padding: 4px 10px; }"
            "QPushButton:hover { border-color: #107c10; color: white; }"
        )
        self.detect_dest_btn.clicked.connect(self._detect_dest)
        s3_top.addWidget(self.detect_dest_btn)
        pl.addLayout(s3_top)

        # Detected path row
        det_row = QHBoxLayout()
        det_row.addWidget(QLabel("Destino Xbox:"))
        self.partition_combo = QComboBox()
        self.partition_combo.setMinimumWidth(160)
        self.partition_combo.currentTextChanged.connect(self._on_dest_combo_changed)
        det_row.addWidget(self.partition_combo)

        self.detected_lbl = QLabel("")
        self.detected_lbl.setStyleSheet("color: #107c10; font-size: 11px; font-family: Consolas;")
        self.detected_lbl.setWordWrap(True)
        det_row.addWidget(self.detected_lbl, 1)

        self.btn_install = QPushButton("Instalar en Xbox")
        self.btn_install.setEnabled(False)
        self.btn_install.setMinimumHeight(34)
        self.btn_install.setStyleSheet(
            "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 7px 14px; }"
            "QPushButton:hover { background: #13a10e; } QPushButton:disabled { background: #1e3a1e; color: #555; }"
        )
        self.btn_install.clicked.connect(self._do_install)
        det_row.addWidget(self.btn_install)
        pl.addLayout(det_row)

        # Per-file progress
        pf_row = QHBoxLayout()
        pf_lbl = QLabel("Archivo:")
        pf_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        pf_lbl.setMinimumWidth(55)
        pf_row.addWidget(pf_lbl)
        self.file_bar = QProgressBar()
        self.file_bar.setMaximum(1000)
        self.file_bar.setValue(0)
        self.file_bar.setFixedHeight(10)
        self.file_bar.setTextVisible(False)
        pf_row.addWidget(self.file_bar, 1)
        self.file_bar_lbl = QLabel("—")
        self.file_bar_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px; min-width: 130px;")
        pf_row.addWidget(self.file_bar_lbl)
        pl.addLayout(pf_row)

        # Overall progress
        ov_row = QHBoxLayout()
        ov_lbl = QLabel("Total:")
        ov_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        ov_lbl.setMinimumWidth(55)
        ov_row.addWidget(ov_lbl)
        self.install_bar = QProgressBar()
        self.install_bar.setMaximum(1000)
        self.install_bar.setValue(0)
        self.install_bar.setFixedHeight(10)
        self.install_bar.setTextVisible(False)
        ov_row.addWidget(self.install_bar, 1)
        self.install_bar_lbl = QLabel("—")
        self.install_bar_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px; min-width: 130px;")
        ov_row.addWidget(self.install_bar_lbl)
        pl.addLayout(ov_row)

        rl.addWidget(pipe)

        # ── Log ───────────────────────────────────────────────────────────────
        log_lbl = QLabel("LOG DE ACTIVIDAD")
        log_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px; font-weight: 600;")
        rl.addWidget(log_lbl)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(
            "QTextEdit { background: #0d0d0d; color: #cccccc; border: 1px solid #2a2a2a; "
            "border-radius: 6px; font-family: Consolas, monospace; font-size: 12px; padding: 6px; }"
        )
        rl.addWidget(self.log_box, 1)

        clr = QPushButton("Limpiar log")
        clr.setMaximumWidth(120)
        clr.clicked.connect(self.log_box.clear)
        rl.addWidget(clr)

        splitter.addWidget(right)
        splitter.setSizes([280, 720])
        layout.addWidget(splitter, 1)

        self._refresh_files()
        self._reset_combo()

    # ── State persistence ─────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        try:
            if os.path.exists(self._state_file):
                with open(self._state_file, encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_state(self):
        try:
            os.makedirs(self.downloads_dir, exist_ok=True)
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(self._processed, f, indent=2)
        except Exception:
            pass

    def _state_key(self, zip_path: str) -> str:
        return os.path.basename(zip_path)

    def _mark_step(self, zip_path: str, step: str, value):
        key = self._state_key(zip_path)
        if key not in self._processed:
            self._processed[key] = {}
        self._processed[key][step] = value
        self._save_state()

    def _get_step(self, zip_path: str, step: str):
        return self._processed.get(self._state_key(zip_path), {}).get(step)

    def showEvent(self, event):
        super().showEvent(event)
        # Auto-detect only if not already detected and no worker is running
        if get_client().connected and not self._detected_dest and not (
                self._detect_worker and self._detect_worker.isRunning()):
            self._detect_dest()

    def _reset_combo(self):
        """Populate combo with fixed manual-fallback options."""
        self.partition_combo.blockSignals(True)
        self.partition_combo.clear()
        self.partition_combo.addItems([
            'F:/GAMES', 'E:/GAMES', 'G:/GAMES',
        ])
        self.partition_combo.blockSignals(False)

    # ── File list ─────────────────────────────────────────────────────────────

    def _refresh_files(self):
        self.files_list.clear()
        os.makedirs(self.downloads_dir, exist_ok=True)
        for f in sorted(os.listdir(self.downloads_dir)):
            if f.lower().endswith('.zip'):
                item = QListWidgetItem(f)
                item.setData(Qt.ItemDataRole.UserRole,
                             os.path.join(self.downloads_dir, f))
                self.files_list.addItem(item)

    def _on_file_selected(self, item):
        if not item:
            self.btn_extract.setEnabled(False)
            return
        self._current_zip      = item.data(Qt.ItemDataRole.UserRole)
        self._current_iso      = None
        self._current_game_dir = None

        self.selected_label.setText(
            f"Seleccionado: {os.path.basename(self._current_zip)}")

        # Restore previous state for this ZIP
        saved_iso      = self._get_step(self._current_zip, 'iso')
        saved_game_dir = self._get_step(self._current_zip, 'game_dir')

        step1_done = saved_iso      and os.path.exists(saved_iso)
        step2_done = saved_game_dir and os.path.exists(saved_game_dir)

        if step1_done:
            self._current_iso = saved_iso
            self.s1_st.setText("✅")
            self._log(f"Paso 1 ya completado: {os.path.basename(saved_iso)}", "#107c10")
        else:
            self.s1_st.setText("⬜")

        if step2_done:
            self._current_game_dir = saved_game_dir
            self.s2_st.setText("✅")
            self._log(f"Paso 2 ya completado: {os.path.basename(saved_game_dir)}", "#107c10")
        else:
            self.s2_st.setText("⬜")

        self.s3_st.setText("⬜")

        extracting  = self._extracting_zip == self._current_zip
        processing  = (self._processing_iso is not None
                       and self._processing_iso == self._get_step(self._current_zip, 'iso'))

        self.btn_extract.setEnabled(not step1_done and not extracting)
        self.btn_xiso.setEnabled(bool(step1_done and not step2_done and not processing))
        self.btn_install.setEnabled(bool(step2_done))
        if extracting:
            self.s1_st.setText("⏳")
        if processing:
            self.s2_st.setText("⏳")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg, color="#cccccc"):
        self.log_box.append(f'<span style="color:{color};">{msg}</span>')

    # ── Step 1: extract ZIP ───────────────────────────────────────────────────

    def _do_extract(self):
        if not self._current_zip:
            return
        game_name = os.path.splitext(os.path.basename(self._current_zip))[0]
        out_dir   = os.path.join(self.downloads_dir, game_name + '_extracted')
        self._extracting_zip = self._current_zip
        self.btn_extract.setEnabled(False)
        self.extract_bar.setVisible(True)
        self.extract_bar.setValue(0)
        self.s1_st.setText("⏳")
        self._log(f"Extrayendo: {os.path.basename(self._current_zip)}", "#f7630c")
        self._extract_worker = ExtractWorker(self._current_zip, out_dir)
        self._extract_worker.progress.connect(
            lambda d, t: self.extract_bar.setValue(int(d * 100 / t)) if t else None)
        self._extract_worker.file_progress.connect(
            lambda f: self._log(f"  {f}", "#555555"))
        self._extract_worker.finished.connect(self._on_extract_done)
        self._extract_worker.error.connect(self._on_extract_err)
        self._extract_worker.start()

    def _on_extract_done(self, out_dir):
        self._extracting_zip = None
        self.extract_bar.setValue(100)
        self.extract_bar.setVisible(False)
        self.s1_st.setText("✅")
        self._log("ZIP extraido correctamente.", "#107c10")
        iso = find_iso_in_dir(out_dir)
        if iso:
            self._current_iso = iso
            self._mark_step(self._current_zip, 'iso', iso)
            self._log(f"ISO encontrada: {os.path.basename(iso)}", "#107c10")
            self.btn_xiso.setEnabled(True)
        else:
            self._log("No se encontro archivo ISO.", "#c42b1c")
        self.btn_extract.setEnabled(True)

    def _on_extract_err(self, msg):
        self._extracting_zip = None
        self.extract_bar.setVisible(False)
        self.s1_st.setText("❌")
        self._log(f"Error: {msg}", "#c42b1c")
        self.btn_extract.setEnabled(True)

    # ── Step 2: extract-xiso ──────────────────────────────────────────────────

    def _do_xiso(self):
        if not self._current_iso:
            return
        self._processing_iso = self._current_iso
        self.btn_xiso.setEnabled(False)
        self.s2_st.setText("⏳")
        self._log("Ejecutando extract-xiso...", "#f7630c")
        self._xiso_worker = XisoWorker(self._current_iso)
        self._xiso_worker.output_line.connect(
            lambda l: self._log(f"  {l}", "#555555"))
        self._xiso_worker.finished.connect(self._on_xiso_done)
        self._xiso_worker.error.connect(self._on_xiso_err)
        self._xiso_worker.start()

    def _on_xiso_done(self, game_dir):
        self._processing_iso = None
        self._current_game_dir = game_dir
        self._mark_step(self._current_zip, 'game_dir', game_dir)
        self.s2_st.setText("✅")
        self._log(f"ISO procesada: {os.path.basename(game_dir)}", "#107c10")
        self.btn_xiso.setEnabled(True)
        self.btn_install.setEnabled(True)
        # Count files for info
        n_files, n_bytes = _count_local(game_dir)
        self._log(
            f"  {n_files} archivos, {_fmt(n_bytes)} total a transferir.",
            "#9e9e9e")

    def _on_xiso_err(self, msg):
        self._processing_iso = None
        self.s2_st.setText("❌")
        self._log(f"Error: {msg}", "#c42b1c")
        self.btn_xiso.setEnabled(True)

    # ── Step 3 destination detection ──────────────────────────────────────────

    def _detect_dest(self):
        client = get_client()
        if not client.connected:
            self._log("Sin conexion FTP. Conéctate primero en la pestaña Xbox FTP.", "#c42b1c")
            return
        self.detect_dest_btn.setEnabled(False)
        self.detect_dest_btn.setText("🔍 Detectando...")
        self._log("Buscando carpeta de juegos en Xbox...", "#9e9e9e")
        self._detect_worker = DetectDestWorker()
        self._detect_worker.result.connect(self._on_dest_detected)
        self._detect_worker.start()

    def _on_dest_detected(self, path):
        self.detect_dest_btn.setEnabled(True)
        self.detect_dest_btn.setText("🔍 Detectar destino")
        if path:
            self._detected_dest = path
            self.detected_lbl.setText(f"✅ {path}")
            self.detected_lbl.setStyleSheet("color: #107c10; font-size: 11px; font-family: Consolas;")
            self._log(f"Carpeta de juegos detectada: {path}", "#107c10")
            # Combo is only used as manual fallback — don't touch it
        else:
            self._detected_dest = ''
            self.detected_lbl.setText("No detectado — elige manualmente")
            self.detected_lbl.setStyleSheet("color: #f7630c; font-size: 11px;")
            self._log("No se encontró carpeta de juegos. Selecciona manualmente.", "#f7630c")

    def _on_dest_combo_changed(self, text):
        # Manual selection overrides auto-detection
        if self._detected_dest:
            self._detected_dest = ''
            self.detected_lbl.setText("Usando selección manual")
            self.detected_lbl.setStyleSheet("color: #9e9e9e; font-size: 11px;")

    def _get_remote_dest(self, game_name: str) -> str:
        """Build the remote path for the game.
        Priority: detected server path > combo value translated via partition map.
        """
        client  = get_client()
        base    = self._detected_dest or self.partition_combo.currentText()

        # If base already looks like a server path (/e/GAMES) use it directly
        if base.startswith('/'):
            return base.rstrip('/') + '/' + game_name

        # combo value like 'F:/GAMES' — translate drive letter to server path
        if len(base) >= 2 and base[1] == ':':
            drive     = base[:2]                     # 'F:'
            subfolder = base[2:].strip('/\\')        # 'GAMES'
            part_path = client.get_partition_path(drive)  # '/f' or '/hdd0-f'
            if subfolder:
                return f"{part_path}/{subfolder}/{game_name}"
            return f"{part_path}/{game_name}"

        # Fallback
        return '/' + base.strip('/') + '/' + game_name

    # ── Step 3: FTP install ───────────────────────────────────────────────────

    def _do_install(self):
        if not self._current_game_dir:
            return
        client = get_client()
        if not client.connected:
            self._log("Sin conexion FTP. Ve a Xbox FTP y conectate.", "#c42b1c")
            return

        game_name = _sanitize_fatx_name(os.path.basename(self._current_game_dir))
        remote    = self._get_remote_dest(game_name)

        self.btn_install.setEnabled(False)
        self.file_bar.setValue(0)
        self.install_bar.setValue(0)
        self.file_bar_lbl.setText("—")
        self.install_bar_lbl.setText("—")
        self.file_bar.setStyleSheet("")
        self.install_bar.setStyleSheet("")
        self.s3_st.setText("⏳")
        self._log(f"Transfiriendo '{game_name}' → {remote}", "#f7630c")

        self._upload_worker = SmartUploadWorker(
            client, self._current_game_dir, remote)

        self._upload_worker.file_started.connect(self._on_file_started)
        self._upload_worker.file_progress.connect(self._on_file_progress)
        self._upload_worker.overall_progress.connect(self._on_overall_progress)
        self._upload_worker.finished.connect(self._on_install_done)
        self._upload_worker.error.connect(self._on_install_err)
        self._upload_worker.start()

    def _on_file_started(self, fname):
        self._log(f"  ↑ {fname}", "#555555")
        self.file_bar.setValue(0)
        self.file_bar_lbl.setText(fname[:28] + '…' if len(fname) > 28 else fname)

    def _on_file_progress(self, fname, done, total):
        if total:
            self.file_bar.setValue(int(done * 1000 / total))
            self.file_bar_lbl.setText(f"{_fmt(done)} / {_fmt(total)}")

    def _on_overall_progress(self, files_done, total_files, bytes_done, total_bytes):
        if total_files:
            self.install_bar.setValue(int(files_done * 1000 / total_files))
        if total_bytes:
            self.install_bar.setValue(int(bytes_done * 1000 / total_bytes))
        self.install_bar_lbl.setText(
            f"{files_done}/{total_files} arch  {_fmt(bytes_done)}")

    def _on_install_done(self):
        self.file_bar.setValue(1000)
        self.install_bar.setValue(1000)
        self.file_bar_lbl.setText("Completado")
        self.install_bar_lbl.setText("Completado")
        self.s3_st.setText("✅")
        self._log("✅ Juego instalado en Xbox correctamente.", "#107c10")
        self.btn_install.setEnabled(True)

    def _on_install_err(self, msg):
        self.s3_st.setText("❌")
        self.file_bar_lbl.setText("Error")
        self.install_bar_lbl.setText("Error")
        self.file_bar.setStyleSheet(
            "QProgressBar { background: #2a0a0a; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: #c42b1c; border-radius: 4px; }"
        )
        self.install_bar.setStyleSheet(
            "QProgressBar { background: #2a0a0a; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: #c42b1c; border-radius: 4px; }"
        )
        self._log(f"❌ Error FTP: {msg}", "#c42b1c")
        self.btn_install.setEnabled(True)
