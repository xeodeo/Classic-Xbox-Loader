"""
Downloads panel - View and manage active/completed downloads.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from core.downloader import get_manager, DownloadTask


def fmt_speed(bps):
    if bps < 1024: return f"{bps:.0f} B/s"
    if bps < 1024**2: return f"{bps/1024:.1f} KB/s"
    return f"{bps/1024**2:.2f} MB/s"

def fmt_size(b):
    if b <= 0: return "?"
    if b < 1024**2: return f"{b/1024:.1f} KB"
    if b < 1024**3: return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"

STATUS_MAP = {
    DownloadTask.PENDING: ("⏳ En espera", "#f7630c"),
    DownloadTask.DOWNLOADING: ("⬇️ Descargando", "#107c10"),
    DownloadTask.PAUSED: ("⏸ Pausado", "#f7630c"),
    DownloadTask.COMPLETED: ("✅ Completado", "#107c10"),
    DownloadTask.ERROR: ("❌ Error", "#c42b1c"),
    DownloadTask.CANCELLED: ("🚫 Cancelado", "#555555"),
}


class DownloadsPanel(QWidget):
    def __init__(self, downloads_dir, parent=None):
        super().__init__(parent)
        self.downloads_dir = downloads_dir
        self._prev_statuses: dict[str, str] = {}   # output_path → last known status
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(400)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        hdr_row = QHBoxLayout()
        header = QLabel("Descargas")
        hf = QFont('Segoe UI', 18)
        hf.setBold(True)
        header.setFont(hf)
        hdr_row.addWidget(header)
        hdr_row.addStretch()

        open_btn = QPushButton("📁  Abrir Carpeta de Descargas")
        open_btn.setStyleSheet(
            "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 9px 18px; }"
            "QPushButton:hover { background: #13a10e; }"
        )
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)
        hdr_row.addWidget(open_btn)
        layout.addLayout(hdr_row)

        self.stats_label = QLabel("No hay descargas activas")
        self.stats_label.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        layout.addWidget(self.stats_label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Juego", "Progreso", "Velocidad", "Tamaño", "Estado", "Acciones"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 220)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 200)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel(
            "⬇️  No hay descargas todavía.\n\nVe al Catálogo 🎮 para buscar y descargar juegos."
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #444; font-size: 14px; padding: 60px;")
        layout.addWidget(self.empty_label)

    def _open_folder(self):
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.startfile(self.downloads_dir)

    def _refresh(self):
        from core import notifier
        manager = get_manager()
        tasks = manager.queue
        # Detect newly completed downloads and notify
        for task in tasks:
            prev = self._prev_statuses.get(task.output_path)
            if prev != task.status:
                if task.status == DownloadTask.COMPLETED and prev == DownloadTask.DOWNLOADING:
                    notifier.notify("Descarga completada", task.game_name)
                self._prev_statuses[task.output_path] = task.status
        has = len(tasks) > 0
        self.empty_label.setVisible(not has)
        self.table.setVisible(has)

        active = [t for t in tasks if t.status == DownloadTask.DOWNLOADING]
        if active:
            self.stats_label.setText(f"{len(active)} activa(s)  •  Velocidad: {fmt_speed(sum(t.speed for t in active))}")
        elif has:
            done = sum(1 for t in tasks if t.status == DownloadTask.COMPLETED)
            self.stats_label.setText(f"{done}/{len(tasks)} completadas")
        else:
            self.stats_label.setText("No hay descargas activas")

        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.table.setRowHeight(row, 50)
            self.table.setItem(row, 0, QTableWidgetItem(task.game_name))

            bar = QProgressBar()
            bar.setMaximum(100)
            if task.total_bytes > 0:
                pct = int(task.bytes_done * 100 / task.total_bytes)
                bar.setValue(pct)
                bar.setFormat(f"{pct}%  ({fmt_size(task.bytes_done)} / {fmt_size(task.total_bytes)})")
            else:
                bar.setValue(0)
                bar.setFormat("Conectando...")
            bar.setStyleSheet(
                "QProgressBar { background: #2a2a2a; border: none; border-radius: 4px; color: white; font-size: 11px; text-align: center; }"
                "QProgressBar::chunk { background: #107c10; border-radius: 4px; }"
            )
            self.table.setCellWidget(row, 1, bar)

            spd = QTableWidgetItem(fmt_speed(task.speed) if task.status == DownloadTask.DOWNLOADING else "—")
            spd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, spd)

            sz = QTableWidgetItem(fmt_size(task.total_bytes))
            sz.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, sz)

            lt, _ = STATUS_MAP.get(task.status, ("?", "#9e9e9e"))
            st = QTableWidgetItem(lt)
            st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, st)

            aw = QWidget()
            aw.setStyleSheet("background: transparent;")
            al = QHBoxLayout(aw)
            al.setContentsMargins(4, 4, 4, 4)
            al.setSpacing(4)

            _btn_base = (
                "QPushButton { border: none; border-radius: 5px; font-size: 15px; "
                "padding: 2px; color: white; }"
            )

            if task.status == DownloadTask.DOWNLOADING:
                pb = QPushButton("⏸")
                pb.setFixedSize(34, 34)
                pb.setToolTip("Pausar")
                pb.setStyleSheet(_btn_base + "QPushButton { background: #f7630c; } QPushButton:hover { background: #ff8c00; }")
                pb.clicked.connect(lambda _, t=task: get_manager().pause(t))
                al.addWidget(pb)

                cb = QPushButton("⏹")
                cb.setFixedSize(34, 34)
                cb.setToolTip("Cancelar descarga")
                cb.setStyleSheet(_btn_base + "QPushButton { background: #c42b1c; } QPushButton:hover { background: #e81123; }")
                cb.clicked.connect(lambda _, t=task: get_manager().cancel(t))
                al.addWidget(cb)

            elif task.status == DownloadTask.PAUSED:
                rb = QPushButton("▶")
                rb.setFixedSize(34, 34)
                rb.setToolTip("Reanudar")
                rb.setStyleSheet(_btn_base + "QPushButton { background: #107c10; } QPushButton:hover { background: #13a10e; }")
                rb.clicked.connect(lambda _, t=task: get_manager().resume(t))
                al.addWidget(rb)

                cb = QPushButton("⏹")
                cb.setFixedSize(34, 34)
                cb.setToolTip("Cancelar descarga")
                cb.setStyleSheet(_btn_base + "QPushButton { background: #c42b1c; } QPushButton:hover { background: #e81123; }")
                cb.clicked.connect(lambda _, t=task: get_manager().cancel(t))
                al.addWidget(cb)

            elif task.status == DownloadTask.PENDING:
                cb = QPushButton("⏹")
                cb.setFixedSize(34, 34)
                cb.setToolTip("Cancelar")
                cb.setStyleSheet(_btn_base + "QPushButton { background: #c42b1c; } QPushButton:hover { background: #e81123; }")
                cb.clicked.connect(lambda _, t=task: get_manager().cancel(t))
                al.addWidget(cb)

            elif task.status == DownloadTask.COMPLETED:
                del_list = QPushButton("✕")
                del_list.setFixedSize(34, 34)
                del_list.setToolTip("Quitar de la lista")
                del_list.setStyleSheet(_btn_base + "QPushButton { background: #3a3a3a; } QPushButton:hover { background: #555; }")
                del_list.clicked.connect(lambda _, t=task: get_manager().remove(t))
                al.addWidget(del_list)

                del_file = QPushButton("🗑")
                del_file.setFixedSize(34, 34)
                del_file.setToolTip("Eliminar archivo del disco")
                del_file.setStyleSheet(_btn_base + "QPushButton { background: #c42b1c; } QPushButton:hover { background: #e81123; }")
                del_file.clicked.connect(lambda _, t=task: get_manager().remove_with_file(t))
                al.addWidget(del_file)

            elif task.status in (DownloadTask.ERROR, DownloadTask.CANCELLED):
                if task.status == DownloadTask.ERROR and task.session is not None:
                    retry_btn = QPushButton("🔄")
                    retry_btn.setFixedSize(34, 34)
                    retry_btn.setToolTip("Reintentar descarga (reanuda desde donde se interrumpió)")
                    retry_btn.setStyleSheet(_btn_base + "QPushButton { background: #107c10; } QPushButton:hover { background: #13a10e; }")
                    retry_btn.clicked.connect(lambda _, t=task: get_manager().retry(t))
                    al.addWidget(retry_btn)

                del_list = QPushButton("✕")
                del_list.setFixedSize(34, 34)
                del_list.setToolTip("Quitar de la lista")
                del_list.setStyleSheet(_btn_base + "QPushButton { background: #3a3a3a; } QPushButton:hover { background: #555; }")
                del_list.clicked.connect(lambda _, t=task: get_manager().remove(t))
                al.addWidget(del_list)

            al.addStretch()
            self.table.setCellWidget(row, 5, aw)
