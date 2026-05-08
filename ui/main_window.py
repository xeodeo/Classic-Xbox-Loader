"""
Main application window with sidebar navigation and stacked content area.
"""
import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget,
    QDialog, QDialogButtonBox, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon


def get_app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


DOWNLOADS_DIR = os.path.join(get_app_dir(), 'downloads')


_NAV_BG_NORMAL  = "QPushButton { background: transparent; border: none; padding: 12px 20px; text-align: left; } QPushButton:hover { background: #252525; }"
_NAV_BG_CHECKED = "QPushButton { background: #107c10; border: none; padding: 12px 20px; text-align: left; font-weight: bold; }"
_COLOR_NORMAL   = QColor('#cccccc')
_COLOR_CHECKED  = QColor('#ffffff')


class NavButton(QPushButton):
    """Sidebar navigation button."""
    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_text}   {label}")
        self.setCheckable(True)
        self.setMinimumHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._apply(False)

    def _apply(self, checked: bool):
        self.setStyleSheet(_NAV_BG_CHECKED if checked else _NAV_BG_NORMAL)
        p = self.palette()
        p.setColor(QPalette.ColorRole.ButtonText, _COLOR_CHECKED if checked else _COLOR_NORMAL)
        self.setPalette(p)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._apply(checked)


def _show_welcome_if_needed(parent=None):
    """Show welcome popup on first launch. Skipped if user checked 'don't show again'."""
    from core import config as _cfg
    cfg = _cfg.load()
    if cfg.get('hide_welcome'):
        return

    dlg = QDialog(parent)
    dlg.setWindowTitle("Classic Xbox Loader")
    dlg.setMinimumWidth(460)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dlg)
    layout.setSpacing(14)
    layout.setContentsMargins(28, 24, 28, 20)

    title = QLabel("Classic Xbox Loader")
    tf = QFont('Segoe UI', 17)
    tf.setBold(True)
    title.setFont(tf)
    title.setStyleSheet("color: #107c10;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)

    sub = QLabel("Descarga, extrae e instala juegos de Xbox Clásico\ndirectamente desde Internet Archive a tu consola.")
    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sub.setStyleSheet("color: #cccccc; font-size: 13px;")
    sub.setWordWrap(True)
    layout.addWidget(sub)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("background: #2a2a2a;")
    sep.setFixedHeight(1)
    layout.addWidget(sep)

    info_lines = [
        ("Desarrollador", "xeodeo"),
        ("Versión", "1.0.2"),
        ("Fuente", "Internet Archive — Redump Xbox Collection"),
        ("Repositorio", "github.com/xeodeo/Classic-Xbox-Loader"),
    ]
    for label, value in info_lines:
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        lbl.setMinimumWidth(100)
        row.addWidget(lbl)
        if label == "Repositorio":
            val = QLabel(f'<a href="https://github.com/xeodeo/Classic-Xbox-Loader" style="color:#107c10;">{value}</a>')
            val.setOpenExternalLinks(True)
        else:
            val = QLabel(value)
            val.setStyleSheet("color: #ffffff; font-size: 12px;")
        row.addWidget(val)
        row.addStretch()
        layout.addLayout(row)

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("background: #2a2a2a;")
    sep2.setFixedHeight(1)
    layout.addWidget(sep2)

    no_show = QCheckBox("No volver a mostrar")
    no_show.setStyleSheet("color: #9e9e9e; font-size: 12px;")
    layout.addWidget(no_show)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    btns.accepted.connect(dlg.accept)
    btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
        "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 8px 28px; font-size: 13px; }"
        "QPushButton:hover { background: #13a10e; }"
    )
    layout.addWidget(btns, alignment=Qt.AlignmentFlag.AlignCenter)

    dlg.exec()

    if no_show.isChecked():
        cfg['hide_welcome'] = True
        _cfg.save(cfg)


def _app_icon() -> QIcon:
    """Load app icon from ICO (built exe) or SVG (dev mode)."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = get_app_dir()
    for name in ('app_icon.ico', 'microsoft-xbox-1.svg'):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Classic Xbox Loader")
        icon = _app_icon()
        self.setWindowIcon(icon)
        self.setMinimumSize(1100, 700)
        self.resize(1300, 820)
        from core import notifier
        notifier.init(icon, self)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: _show_welcome_if_needed(self))

        from ui.catalog_panel import CatalogPanel
        from ui.downloads_panel import DownloadsPanel
        from ui.install_panel import InstallPanel
        from ui.ftp_panel import FTPPanel
        from ui.settings_panel import SettingsPanel

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo area
        logo_container = QWidget()
        logo_container.setFixedHeight(90)
        logo_container.setStyleSheet("background-color: #0f0f0f; border-bottom: 1px solid #2a2a2a;")
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 0, 16, 0)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_label = QLabel("🎮  Classic Xbox Loader")
        logo_font = QFont('Segoe UI', 12)
        logo_font.setBold(True)
        logo_label.setFont(logo_font)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("color: #107c10; background: transparent;")
        logo_layout.addWidget(logo_label)
        sidebar_layout.addWidget(logo_container)

        # Nav buttons
        self.nav_buttons = []
        self.stack = QStackedWidget()

        panels = [
            CatalogPanel(DOWNLOADS_DIR),
            DownloadsPanel(DOWNLOADS_DIR),
            InstallPanel(DOWNLOADS_DIR),
            FTPPanel(),
            SettingsPanel(),
        ]

        nav_items = [
            ("🎮", "Catálogo"),
            ("⬇️", "Descargas"),
            ("📦", "Instalación"),
            ("🔗", "Xbox FTP"),
            ("⚙️", "Configuración"),
        ]

        sidebar_layout.addSpacing(8)
        for i, (icon, label) in enumerate(nav_items):
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda checked, idx=i: self._switch_panel(idx))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)
            self.stack.addWidget(panels[i])

        sidebar_layout.addStretch()

        ver_label = QLabel("v1.0.2")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_label.setStyleSheet("color: #444444; padding: 12px; font-size: 11px; background: transparent;")
        sidebar_layout.addWidget(ver_label)

        main_layout.addWidget(sidebar)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("background: #2a2a2a; max-width: 1px;")
        main_layout.addWidget(divider)

        main_layout.addWidget(self.stack, 1)

        self._switch_panel(0)

    def _switch_panel(self, index: int):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)
