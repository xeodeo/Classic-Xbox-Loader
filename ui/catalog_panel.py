"""
Catalog panel - Browse and download Xbox games from Internet Archive.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from core import catalog
from core.auth import get_session
from core.downloader import get_manager


class FetchWorker(QThread):
    result = pyqtSignal(list)
    status = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, letter):
        super().__init__()
        self.letter = letter

    def run(self):
        try:
            games = catalog.fetch_letter(self.letter, progress_callback=lambda m: self.status.emit(m))
            self.result.emit(games)
        except Exception as e:
            self.error.emit(str(e))


class CatalogPanel(QWidget):
    def __init__(self, downloads_dir, parent=None):
        super().__init__(parent)
        self.downloads_dir = downloads_dir
        self._all_games = []
        self._fetch_worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        hdr_row = QHBoxLayout()
        header = QLabel("Catálogo de Juegos")
        hf = QFont('Segoe UI', 18)
        hf.setBold(True)
        header.setFont(hf)
        hdr_row.addWidget(header)
        hdr_row.addStretch()
        self.status_label = QLabel("Selecciona una letra")
        self.status_label.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        hdr_row.addWidget(self.status_label)
        layout.addLayout(hdr_row)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍   Buscar juego por nombre...")
        self.search_input.setMinimumHeight(40)
        self.search_input.textChanged.connect(self._filter_games)
        layout.addWidget(self.search_input)

        letters_widget = QWidget()
        letters_widget.setStyleSheet("background: transparent;")
        ll = QHBoxLayout(letters_widget)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(3)

        self._letter_buttons = {}
        for letter in ['#'] + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
            btn = QPushButton(letter)
            btn.setFixedSize(34, 34)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: #2a2a2a; color: white; border: 1px solid #333; border-radius: 4px; font-size: 12px; font-weight: bold; padding: 0px; }"
                "QPushButton:hover { background: #353535; border-color: #107c10; color: white; }"
                "QPushButton:checked { background: #107c10; border-color: #107c10; color: white; }"
            )
            btn.clicked.connect(lambda checked, l=letter: self._load_letter(l))
            ll.addWidget(btn)
            self._letter_buttons[letter] = btn
        ll.addStretch()
        layout.addWidget(letters_widget)

        self.loading_label = QLabel("")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #107c10; font-size: 13px;")
        layout.addWidget(self.loading_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Nombre del Juego", "Tamaño", "Acción"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 130)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel(
            "🎮  Selecciona una letra del alfabeto para ver los juegos disponibles.\n\n"
            "Los juegos se cargan desde Internet Archive (Redump.org collection)."
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #444; font-size: 14px; padding: 60px;")
        layout.addWidget(self.empty_label)

    def _load_letter(self, letter):
        for l, btn in self._letter_buttons.items():
            btn.setChecked(l == letter)
        self._all_games = []
        self.table.setRowCount(0)
        self.search_input.clear()
        self.empty_label.setVisible(False)
        self.loading_label.setText(f"⏳  Cargando juegos con '{letter}'...")
        self.status_label.setText("Cargando...")

        if self._fetch_worker and self._fetch_worker.isRunning():
            self._fetch_worker.terminate()
            self._fetch_worker.wait()

        self._fetch_worker = FetchWorker(letter)
        self._fetch_worker.result.connect(self._on_games_loaded)
        self._fetch_worker.status.connect(lambda m: self.loading_label.setText(f"⏳  {m}"))
        self._fetch_worker.error.connect(self._on_error)
        self._fetch_worker.start()

    def _on_games_loaded(self, games):
        self._all_games = games
        self.loading_label.setText("")
        n = len(games)
        self.status_label.setText(f"{n} juego{'s' if n != 1 else ''} encontrado{'s' if n != 1 else ''}")
        self._populate_table(games)

    def _on_error(self, msg):
        self.loading_label.setText(f"❌  Error: {msg}")
        self.status_label.setText("Error")

    def _filter_games(self, query):
        self._populate_table(catalog.search_games(self._all_games, query))

    def _populate_table(self, games):
        self.table.setRowCount(0)
        self.table.setRowCount(len(games))
        for row, game in enumerate(games):
            self.table.setItem(row, 0, QTableWidgetItem(game['display_name']))
            si = QTableWidgetItem(game['size_str'])
            si.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, si)
            dl_btn = QPushButton("⬇  Descargar")
            dl_btn.setStyleSheet(
                "QPushButton { background: #107c10; color: white; border: none; border-radius: 5px; padding: 5px 12px; font-size: 12px; }"
                "QPushButton:hover { background: #13a10e; }"
                "QPushButton:pressed { background: #0a5c0a; }"
            )
            dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            dl_btn.clicked.connect(lambda _, g=game: self._download_game(g))
            self.table.setCellWidget(row, 2, dl_btn)
            self.table.setRowHeight(row, 42)

    def _download_game(self, game):
        if not get_session().logged_in:
            QMessageBox.warning(
                self, "Inicia sesión para descargar",
                "Necesitas iniciar sesión en Internet Archive para descargar juegos.\n\n"
                "Ve a ⚙️ Configuración → Iniciar sesión con tu cuenta."
            )
            return
        os.makedirs(self.downloads_dir, exist_ok=True)
        output_path = os.path.join(self.downloads_dir, game['name'])
        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self, "Archivo existente",
                f"'{game['display_name']}' ya existe. ¿Descargar de nuevo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        session = get_session().get_session()
        manager = get_manager()
        task = manager.add_download(game['url'], output_path, game['display_name'], session)
        manager.start(task)
        QMessageBox.information(self, "Descarga iniciada",
            f"'{game['display_name']}' añadido a la cola.\n\nVe a ⬇️ Descargas para ver el progreso.")
