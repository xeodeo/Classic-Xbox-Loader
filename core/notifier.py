"""
Sistema de notificaciones via system tray.
notify() puede llamarse desde cualquier hilo.
"""
from PyQt6.QtWidgets import QSystemTrayIcon
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

_tray: QSystemTrayIcon | None = None


def init(icon: QIcon, parent=None):
    """Llamar una sola vez al iniciar la app, desde el hilo principal."""
    global _tray
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    _tray = QSystemTrayIcon(icon, parent)
    _tray.show()


def notify(title: str, message: str):
    """Mostrar notificación si están habilitadas. Thread-safe via QTimer."""
    from core import config as _cfg
    if not _cfg.load().get('notifications_enabled', True):
        return
    if _tray is None:
        return
    # QTimer.singleShot despacha al hilo principal desde cualquier hilo
    QTimer.singleShot(0, lambda: _tray.showMessage(
        title, message, QSystemTrayIcon.MessageIcon.Information, 5000
    ))
