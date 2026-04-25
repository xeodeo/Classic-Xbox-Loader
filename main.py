"""
Classic Xbox Loader - Main entry point.
"""
import sys
import os
import logging

# Configure logging
log_handlers = [logging.StreamHandler()]
try:
    log_handlers.append(logging.FileHandler('xbox_loader.log', encoding='utf-8'))
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=log_handlers
)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
# QtWebEngineWidgets MUST be imported before QApplication is created.
# If not done here, the import inside settings_panel.py fails silently.
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView as _  # noqa: F401
except Exception:
    pass
from ui.main_window import MainWindow
from ui.styles import DARK_STYLE


def _find_icon() -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    for name in ('app_icon.ico', 'microsoft-xbox-1.svg'):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return ''


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Classic Xbox Loader")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("XboxLoader")
    icon_path = _find_icon()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
