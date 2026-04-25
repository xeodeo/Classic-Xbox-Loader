"""
FTP panel - Connect and manage Xbox filesystem.
Supports browsing, create/delete/rename folders, upload, download to PC,
and auto-detection of the games folder.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QAbstractItemView, QMessageBox,
    QInputDialog, QFileDialog, QProgressDialog, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from core.ftp_client import get_client, XBOX_PARTITIONS


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b/1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"


# ── Workers ──────────────────────────────────────────────────────────────────

class ConnectWorker(QThread):
    result = pyqtSignal(bool, str)
    def __init__(self, host, port, user, pw):
        super().__init__()
        self.host = host; self.port = port; self.user = user; self.pw = pw
    def run(self):
        ok, msg = get_client().connect(self.host, self.port, self.user, self.pw)
        self.result.emit(ok, msg)


class ListWorker(QThread):
    result = pyqtSignal(str, list)   # actual_path, entries
    error = pyqtSignal(str)
    def __init__(self, path):
        super().__init__()
        self.path = path
    def run(self):
        try:
            client = get_client()
            entries = client.list_dir(self.path)
            # list_dir already cwd'd — use requested path as canonical
            self.result.emit(self.path, entries)
        except Exception as e:
            self.error.emit(str(e))


class DetectGamesWorker(QThread):
    result = pyqtSignal(str)
    def run(self):
        path = get_client().detect_games_folder()
        self.result.emit(path)


class FTPDownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, remote_path, local_path):
        super().__init__()
        self.remote_path = remote_path
        self.local_path = local_path
    def run(self):
        ok, result = get_client().download_file(
            self.remote_path, self.local_path,
            progress_callback=lambda d, t: self.progress.emit(d, t)
        )
        if ok:
            self.finished.emit(result)
        else:
            self.error.emit(result)


# ── Main Panel ────────────────────────────────────────────────────────────────

class FTPPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._list_worker = None
        self._detect_worker = None
        self._dl_worker = None
        self._path_stack = []
        self._current_path = '/'
        self._current_entries = []
        self._was_connected = False
        self._setup_ui()
        # Detect external disconnections (e.g. dropped during FTP upload)
        self._conn_check_timer = QTimer(self)
        self._conn_check_timer.setInterval(2000)
        self._conn_check_timer.timeout.connect(self._check_connection_state)
        self._conn_check_timer.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        header = QLabel("Administrador de Archivos Xbox")
        hf = QFont('Segoe UI', 18)
        hf.setBold(True)
        header.setFont(hf)
        layout.addWidget(header)

        # ── Connection ──────────────────────────────────────────────────────
        conn_group = QGroupBox("Conexión al Xbox")
        cl = QHBoxLayout(conn_group)
        cl.setSpacing(8)

        cl.addWidget(QLabel("IP:"))
        self.ip_input = QLineEdit("192.168.1.100")
        self.ip_input.setMaximumWidth(145)
        self.ip_input.setMinimumHeight(34)
        self.ip_input.returnPressed.connect(self._toggle_connect)
        cl.addWidget(self.ip_input)

        cl.addWidget(QLabel("Puerto:"))
        self.port_input = QLineEdit("21")
        self.port_input.setMaximumWidth(50)
        self.port_input.setMinimumHeight(34)
        cl.addWidget(self.port_input)

        cl.addWidget(QLabel("Usuario:"))
        self.user_input = QLineEdit("xbox")
        self.user_input.setMaximumWidth(80)
        self.user_input.setMinimumHeight(34)
        cl.addWidget(self.user_input)

        cl.addWidget(QLabel("Contraseña:"))
        self.pass_input = QLineEdit("xbox")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setMaximumWidth(80)
        self.pass_input.setMinimumHeight(34)
        self.pass_input.returnPressed.connect(self._toggle_connect)
        cl.addWidget(self.pass_input)

        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.setMinimumHeight(34)
        self.connect_btn.setMinimumWidth(100)
        self.connect_btn.setStyleSheet(
            "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
            "QPushButton:hover { background: #13a10e; }"
        )
        self.connect_btn.clicked.connect(self._toggle_connect)
        cl.addWidget(self.connect_btn)

        self.conn_status = QLabel("● Desconectado")
        self.conn_status.setStyleSheet("color: #c42b1c; font-weight: bold;")
        cl.addWidget(self.conn_status)

        self.detect_games_btn = QPushButton("🎮  Detectar carpeta de juegos")
        self.detect_games_btn.setEnabled(False)
        self.detect_games_btn.setMinimumHeight(34)
        self.detect_games_btn.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #cccccc; border: 1px solid #3a3a3a; border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover { background: #353535; border-color: #107c10; }"
            "QPushButton:disabled { color: #555; }"
        )
        self.detect_games_btn.clicked.connect(self._detect_games)
        cl.addWidget(self.detect_games_btn)
        cl.addStretch()
        layout.addWidget(conn_group)

        # ── Navigation bar ──────────────────────────────────────────────────
        nav = QHBoxLayout()
        nav.setSpacing(6)

        self.back_btn = QPushButton("⬅")
        self.back_btn.setFixedSize(36, 32)
        self.back_btn.setEnabled(False)
        self.back_btn.setToolTip("Atrás")
        self.back_btn.clicked.connect(self._go_back)
        nav.addWidget(self.back_btn)

        nav.addWidget(QLabel("Partición:"))
        self.partition_combo = QComboBox()
        self.partition_combo.addItems(XBOX_PARTITIONS)
        self.partition_combo.setMaximumWidth(80)
        self.partition_combo.currentTextChanged.connect(self._browse_partition)
        nav.addWidget(self.partition_combo)

        self.path_lbl = QLabel("/")
        self.path_lbl.setStyleSheet(
            "color: #107c10; font-family: Consolas; font-size: 12px; "
            "background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 4px; padding: 3px 8px;"
        )
        self.path_lbl.setMinimumWidth(220)
        nav.addWidget(self.path_lbl, 1)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(36, 32)
        self.refresh_btn.setToolTip("Actualizar")
        self.refresh_btn.clicked.connect(self._refresh)
        nav.addWidget(self.refresh_btn)

        layout.addLayout(nav)

        # ── Action toolbar ──────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(6)

        def _action_btn(text, tooltip, slot, color=None):
            b = QPushButton(text)
            b.setMinimumHeight(32)
            b.setToolTip(tooltip)
            b.setEnabled(False)
            if color:
                b.setStyleSheet(
                    f"QPushButton {{ background: {color}; color: white; border: none; border-radius: 5px; padding: 4px 12px; }}"
                    f"QPushButton:hover {{ background: {'#e81123' if color == '#c42b1c' else '#13a10e'}; }}"
                    "QPushButton:disabled { background: #1e1e1e; color: #555; border: 1px solid #2a2a2a; }"
                )
            b.clicked.connect(slot)
            actions.addWidget(b)
            return b

        self.mkdir_btn  = _action_btn("📁  Nueva carpeta", "Crear nueva carpeta en el Xbox", self._mkdir)
        self.rename_btn = _action_btn("✏️  Renombrar",     "Renombrar archivo o carpeta",    self._rename)
        self.delete_btn = _action_btn("🗑  Eliminar",      "Eliminar seleccionado",          self._delete, '#c42b1c')
        self.pc_dl_btn  = _action_btn("⬇  Descargar a PC","Descargar archivo al PC",        self._download_to_pc)
        actions.addStretch()

        self.items_lbl = QLabel("")
        self.items_lbl.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        actions.addWidget(self.items_lbl)

        layout.addLayout(actions)

        # ── File table ───────────────────────────────────────────────────────
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(["Nombre", "Tipo", "Tamaño"])
        hdr = self.file_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setShowGrid(False)
        self.file_table.doubleClicked.connect(self._on_dbl_click)
        self.file_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.file_table.setVisible(False)
        layout.addWidget(self.file_table, 1)

        self.no_conn_lbl = QLabel(
            "🔗  Conecta al Xbox para administrar el sistema de archivos.\n\n"
            "Credenciales por defecto:\n  Usuario: xbox    Contraseña: xbox    Puerto: 21\n\n"
            "Funciones disponibles:\n"
            "  • Explorar todas las particiones (C, E, F, G, X, Y, Z)\n"
            "  • Crear y eliminar carpetas\n"
            "  • Renombrar archivos y carpetas\n"
            "  • Descargar archivos del Xbox al PC\n"
            "  • Auto-detectar carpeta de juegos"
        )
        self.no_conn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_conn_lbl.setStyleSheet("color: #444; font-size: 13px; padding: 40px; line-height: 1.6;")
        layout.addWidget(self.no_conn_lbl)

        self.status_bar = QLabel("")
        self.status_bar.setStyleSheet("color: #9e9e9e; font-size: 11px; padding: 2px;")
        layout.addWidget(self.status_bar)

    # ── Connection ────────────────────────────────────────────────────────────

    def _check_connection_state(self):
        """Detect if the FTP connection was dropped externally (e.g. during upload)."""
        now = get_client().connected
        if self._was_connected and not now:
            self._set_connected(False, "Conexión perdida — reconéctate")
        self._was_connected = now

    def _toggle_connect(self):
        client = get_client()
        if client.connected:
            client.disconnect()
            self._set_connected(False, "Desconectado")
            return
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Conectando...")
        self.conn_status.setText("● Conectando...")
        self.conn_status.setStyleSheet("color: #f7630c; font-weight: bold;")
        try:
            port = int(self.port_input.text())
        except ValueError:
            port = 21
        self._worker = ConnectWorker(
            self.ip_input.text().strip(), port,
            self.user_input.text().strip(), self.pass_input.text()
        )
        self._worker.result.connect(self._on_connect)
        self._worker.start()

    def _on_connect(self, ok, msg):
        self.connect_btn.setEnabled(True)
        self._was_connected = ok
        self._set_connected(ok, msg)
        if ok:
            self._browse_partition(self.partition_combo.currentText())

    def _set_connected(self, connected, msg):
        action_btns = [self.mkdir_btn, self.rename_btn, self.delete_btn,
                       self.pc_dl_btn, self.detect_games_btn]
        if connected:
            self.conn_status.setText(f"● {msg}")
            self.conn_status.setStyleSheet("color: #107c10; font-weight: bold;")
            self.connect_btn.setText("Desconectar")
            self.connect_btn.setStyleSheet(
                "QPushButton { background: #c42b1c; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
                "QPushButton:hover { background: #e81123; }"
            )
            self.file_table.setVisible(True)
            self.no_conn_lbl.setVisible(False)
            self.detect_games_btn.setEnabled(True)
        else:
            self.conn_status.setText(f"● {msg}")
            self.conn_status.setStyleSheet("color: #c42b1c; font-weight: bold;")
            self.connect_btn.setText("Conectar")
            self.connect_btn.setStyleSheet(
                "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
                "QPushButton:hover { background: #13a10e; }"
            )
            self.file_table.setVisible(False)
            self.no_conn_lbl.setVisible(True)
            self.file_table.setRowCount(0)
            for b in action_btns:
                b.setEnabled(False)
            self.items_lbl.setText("")
            self.status_bar.setText("")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _browse_partition(self, part):
        # Ask the client for the actual server path (/e, /hdd0-e, etc.)
        path = get_client().get_partition_path(part)
        self._path_stack = []
        self._navigate(path)

    def _navigate(self, path):
        if not get_client().connected:
            return
        self.status_bar.setText(f"Cargando {path}...")
        if self._list_worker and self._list_worker.isRunning():
            self._list_worker.terminate()
            self._list_worker.wait()
        self._list_worker = ListWorker(path)
        self._list_worker.result.connect(self._on_listed)
        self._list_worker.error.connect(lambda e: self.status_bar.setText(f"Error: {e}"))
        self._list_worker.start()

    def _on_listed(self, actual_path, entries):
        self._current_path = actual_path
        self._current_entries = entries
        self.path_lbl.setText(actual_path)
        self.back_btn.setEnabled(len(self._path_stack) > 0)
        self._populate(entries)
        n = len(entries)
        self.status_bar.setText(f"{n} elemento(s)  |  {actual_path}")
        self.items_lbl.setText(f"{n} elemento(s)")

    def _populate(self, entries):
        self.file_table.setRowCount(0)
        self.file_table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            icon = "📁" if e['is_dir'] else "📄"
            ni = QTableWidgetItem(f"{icon}  {e['name']}")
            ni.setData(Qt.ItemDataRole.UserRole, e)
            self.file_table.setItem(row, 0, ni)
            ti = QTableWidgetItem("Carpeta" if e['is_dir'] else "Archivo")
            ti.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(row, 1, ti)
            size_str = "—" if e['is_dir'] else _fmt_size(e['size'])
            si = QTableWidgetItem(size_str)
            si.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.file_table.setItem(row, 2, si)
            self.file_table.setRowHeight(row, 34)

    def _on_dbl_click(self, index):
        item = self.file_table.item(index.row(), 0)
        if not item:
            return
        e = item.data(Qt.ItemDataRole.UserRole)
        if e and e['is_dir']:
            self._path_stack.append(self._current_path)
            self._navigate(e['path'])

    def _on_selection_changed(self):
        has_sel = bool(self.file_table.selectedItems())
        self.rename_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)
        # Only enable PC download for files
        entry = self._selected_entry()
        self.pc_dl_btn.setEnabled(entry is not None and not entry['is_dir'])

    def _go_back(self):
        if self._path_stack:
            self._navigate(self._path_stack.pop())

    def _refresh(self):
        self._navigate(self._current_path)

    def _selected_entry(self):
        rows = self.file_table.selectedItems()
        if not rows:
            return None
        item = self.file_table.item(self.file_table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ── File operations ───────────────────────────────────────────────────────

    def _mkdir(self):
        name, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre de la carpeta:")
        if not ok or not name.strip():
            return
        path = self._current_path.rstrip('/') + '/' + name.strip()
        success, msg = get_client().mkdir(path)
        if success:
            self.status_bar.setText(f"✅  Carpeta '{name}' creada")
            self._refresh()
        else:
            QMessageBox.warning(self, "Error", f"No se pudo crear la carpeta:\n{msg}")

    def _rename(self):
        entry = self._selected_entry()
        if not entry:
            return
        new_name, ok = QInputDialog.getText(
            self, "Renombrar", "Nuevo nombre:", text=entry['name']
        )
        if not ok or not new_name.strip() or new_name.strip() == entry['name']:
            return
        success, msg = get_client().rename(entry['path'], new_name.strip())
        if success:
            self.status_bar.setText(f"✅  Renombrado a '{new_name}'")
            self._refresh()
        else:
            QMessageBox.warning(self, "Error", f"No se pudo renombrar:\n{msg}")

    def _delete(self):
        entry = self._selected_entry()
        if not entry:
            return
        kind = "carpeta y todo su contenido" if entry['is_dir'] else "archivo"
        reply = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar el {kind} '{entry['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.status_bar.setText(f"Eliminando '{entry['name']}'...")
        QApplication.processEvents()
        if entry['is_dir']:
            ok, msg = get_client().delete_dir(entry['path'])
        else:
            ok, msg = get_client().delete_file(entry['path'])
        if ok:
            self.status_bar.setText(f"✅  '{entry['name']}' eliminado")
            self._refresh()
        else:
            QMessageBox.warning(self, "Error", f"No se pudo eliminar:\n{msg}")

    def _download_to_pc(self):
        entry = self._selected_entry()
        if not entry or entry['is_dir']:
            return
        local_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar archivo en PC", entry['name']
        )
        if not local_path:
            return

        progress = QProgressDialog(
            f"Descargando '{entry['name']}' del Xbox...", "Cancelar", 0, 100, self
        )
        progress.setWindowTitle("Descargando del Xbox")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        self._dl_worker = FTPDownloadWorker(entry['path'], local_path)

        def on_progress(done, total):
            if total:
                progress.setValue(int(done * 100 / total))
            QApplication.processEvents()

        def on_finished(path):
            progress.close()
            self.status_bar.setText(f"✅  Descargado a: {path}")
            QMessageBox.information(self, "Descarga completa",
                f"Archivo guardado en:\n{path}")

        def on_error(msg):
            progress.close()
            QMessageBox.warning(self, "Error de descarga", msg)

        self._dl_worker.progress.connect(on_progress)
        self._dl_worker.finished.connect(on_finished)
        self._dl_worker.error.connect(on_error)
        self._dl_worker.start()

    # ── Auto-detect games folder ──────────────────────────────────────────────

    def _detect_games(self):
        if not get_client().connected:
            return
        self.detect_games_btn.setEnabled(False)
        self.detect_games_btn.setText("🔍  Detectando...")
        self.status_bar.setText("Buscando carpeta de juegos en el Xbox...")

        self._detect_worker = DetectGamesWorker()
        self._detect_worker.result.connect(self._on_detected_manual)
        self._detect_worker.start()

    def _on_detected_manual(self, path):
        self.detect_games_btn.setEnabled(True)
        self.detect_games_btn.setText("🎮  Detectar carpeta de juegos")
        if path:
            self.status_bar.setText(f"🎮  Carpeta de juegos: {path}")
            reply = QMessageBox.question(
                self, "Carpeta de juegos detectada",
                f"Se encontró la carpeta de juegos en:\n\n{path}\n\n¿Ir a esa carpeta?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # path is like "E:/GAMES" → select partition E: and navigate
                part_letter = path[:2].upper()  # "E:"
                if part_letter in XBOX_PARTITIONS:
                    # Block signal to avoid re-triggering _browse_partition
                    self.partition_combo.blockSignals(True)
                    self.partition_combo.setCurrentIndex(XBOX_PARTITIONS.index(part_letter))
                    self.partition_combo.blockSignals(False)
                self._path_stack = []
                self._navigate(path)
        else:
            QMessageBox.information(
                self, "No encontrado",
                "No se encontró una carpeta de juegos en las particiones E, F y G.\n\n"
                "Verifica que los juegos estén instalados y navega manualmente."
            )
