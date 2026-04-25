"""
Settings panel - Configure Internet Archive login and app preferences.
"""
import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QGroupBox, QSpinBox, QFrame, QScrollArea, QDialog,
    QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QFont
from core.auth import get_session
import core.downloader as dl_module
from core import config as _cfg

_WEBENGINE_AVAILABLE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineProfile
    _WEBENGINE_AVAILABLE = True
except ImportError:
    pass


class LoginWorker(QThread):
    result = pyqtSignal(bool, str)
    def __init__(self, email, password):
        super().__init__()
        self.email = email; self.password = password
    def run(self):
        ok, msg = get_session().login(self.email, self.password)
        self.result.emit(ok, msg)


class WebLoginDialog(QDialog):
    """Opens archive.org login page in an embedded browser for Google/email login."""
    login_detected = pyqtSignal(str)  # username

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Iniciar sesión — Internet Archive")
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)

        if not _WEBENGINE_AVAILABLE:
            lbl = QLabel(
                "PyQt6-WebEngine no está instalado.\n"
                "Ejecuta: pip install PyQt6-WebEngine"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            btn = QPushButton("Cerrar")
            btn.clicked.connect(self.reject)
            layout.addWidget(btn)
            return

        self._cookies = {}  # Accumulates ALL archive.org cookies during the session

        self._view = QWebEngineView()
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._view)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        # Connect cookieAdded BEFORE loading the page so no cookie is missed,
        # including those set during Google OAuth redirects.
        cookie_store = self._view.page().profile().cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)
        cookie_store.loadAllCookies()

        self._view.load(QUrl("https://archive.org/account/login"))

        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._check_login)
        self._timer.start()

    def _on_cookie_added(self, cookie):
        """Called for every cookie set in the browser — including Google OAuth ones."""
        if 'archive.org' in cookie.domain():
            name  = cookie.name().data().decode('utf-8', errors='replace')
            value = cookie.value().data().decode('utf-8', errors='replace')
            self._cookies[name] = value

    def _check_login(self):
        current_url = self._view.url().toString()
        if 'archive.org' in current_url and 'account/login' not in current_url:
            self._timer.stop()
            # Wait for post-redirect cookies to arrive before finalizing
            QTimer.singleShot(1500, self._finalize_login)

    def _finalize_login(self):
        # Request one more cookie flush, then apply after a short delay
        self._view.page().profile().cookieStore().loadAllCookies()
        QTimer.singleShot(500, self._apply_login)

    def _apply_login(self):
        from urllib.parse import unquote
        cookies = self._cookies
        session = get_session()
        session.session.cookies.update(cookies)

        username = unquote(cookies.get('logged-in-user', ''))
        if not username:
            username = self._view.page().title() or 'Usuario'

        if cookies.get('logged-in-sig') or cookies.get('logged-in-user'):
            session.logged_in = True
            session.username = username
            session.save_session()
            self.login_detected.emit(username)
            self.accept()
        else:
            # Not detected yet — resume polling
            self._timer.start()


class SettingsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._setup_ui()
        self._refresh_session_ui()

    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        header = QLabel("Configuración")
        hf = QFont('Segoe UI', 18)
        hf.setBold(True)
        header.setFont(hf)
        layout.addWidget(header)

        # Internet Archive
        ia_group = QGroupBox("Internet Archive — Autenticación")
        ia_l = QVBoxLayout(ia_group)
        ia_l.setSpacing(10)

        desc = QLabel(
            "Inicia sesión para obtener descargas más rápidas. "
            "En modo anónimo las velocidades pueden ser limitadas."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        ia_l.addWidget(desc)

        self.ia_status = QLabel("● Modo anónimo (sin sesión)")
        self.ia_status.setStyleSheet("color: #f7630c; font-weight: bold; font-size: 13px;")
        ia_l.addWidget(self.ia_status)

        form = QHBoxLayout()
        form.setSpacing(10)
        form.addWidget(QLabel("Email:"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("tu@email.com")
        self.email_input.setMinimumHeight(36)
        self.email_input.setMinimumWidth(200)
        form.addWidget(self.email_input)

        form.addWidget(QLabel("Contraseña:"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("••••••••")
        self.pass_input.setMinimumHeight(36)
        self.pass_input.setMinimumWidth(160)
        self.pass_input.returnPressed.connect(self._toggle_login)
        form.addWidget(self.pass_input)

        self.login_btn = QPushButton("Iniciar sesión")
        self.login_btn.setMinimumHeight(36)
        self.login_btn.setMinimumWidth(130)
        self.login_btn.setStyleSheet(
            "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
            "QPushButton:hover { background: #13a10e; }"
        )
        self.login_btn.clicked.connect(self._toggle_login)
        form.addWidget(self.login_btn)

        self.google_btn = QPushButton("🌐  Login con Google / Navegador")
        self.google_btn.setMinimumHeight(36)
        self.google_btn.setMinimumWidth(200)
        self.google_btn.setStyleSheet(
            "QPushButton { background: #1a73e8; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
            "QPushButton:hover { background: #1557b0; }"
        )
        self.google_btn.clicked.connect(self._open_web_login)
        form.addWidget(self.google_btn)
        form.addStretch()
        ia_l.addLayout(form)

        self.login_msg = QLabel("")
        self.login_msg.setStyleSheet("font-size: 12px;")
        ia_l.addWidget(self.login_msg)
        layout.addWidget(ia_group)

        # Downloads
        dl_group = QGroupBox("Descargas — Rendimiento")
        dl_l = QVBoxLayout(dl_group)
        tr = QHBoxLayout()
        tr.addWidget(QLabel("Hilos de descarga simultáneos (1-16):"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 16)
        self.threads_spin.setValue(dl_module.NUM_THREADS)
        self.threads_spin.setMinimumWidth(80)
        self.threads_spin.setMinimumHeight(34)
        self.threads_spin.setToolTip("Mayor número = descarga más rápida")
        self.threads_spin.valueChanged.connect(self._on_threads_changed)
        tr.addWidget(self.threads_spin)
        tr.addWidget(QLabel("(5 recomendado)"))
        tr.addStretch()
        dl_l.addLayout(tr)
        layout.addWidget(dl_group)

        # Paths
        paths_group = QGroupBox("Rutas del sistema")
        paths_l = QVBoxLayout(paths_group)
        app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
            else os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

        for label_text, path in [
            ("Carpeta de descargas", os.path.join(app_dir, 'downloads')),
            ("extract-xiso.exe", os.path.join(app_dir, 'extract iso a xiso', 'extract-xiso.exe')),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}:")
            lbl.setMinimumWidth(180)
            lbl.setStyleSheet("color: #9e9e9e;")
            row.addWidget(lbl)
            pl = QLabel(path)
            pl.setStyleSheet("color: #107c10; font-family: Consolas; font-size: 11px;")
            pl.setWordWrap(True)
            row.addWidget(pl, 1)
            el = QLabel("✅" if os.path.exists(path) else "❌")
            row.addWidget(el)
            paths_l.addLayout(row)
        layout.addWidget(paths_group)

        # About
        about_group = QGroupBox("Acerca de")
        about_l = QVBoxLayout(about_group)
        about_text = QLabel(
            "<b style='color:#107c10; font-size:15px;'>Classic Xbox Loader v1.0.0</b><br><br>"
            "Descarga, procesa e instala juegos en Xbox Classic automáticamente.<br><br>"
            "<b>Fuente:</b> Internet Archive (Redump.org Xbox Collection)<br>"
            "<b>Procesamiento:</b> extract-xiso.exe<br>"
            "<b>Instalación:</b> FTP a Xbox con chip mod<br><br>"
            "<span style='color:#9e9e9e; font-size:11px;'>Solo contenido públicamente disponible.</span>"
        )
        about_text.setWordWrap(True)
        about_l.addWidget(about_text)
        layout.addWidget(about_group)

        layout.addStretch()
        scroll.setWidget(content)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _toggle_login(self):
        session = get_session()
        if session.logged_in:
            session.logout()
            self.login_btn.setText("Iniciar sesión")
            self.login_btn.setStyleSheet(
                "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
                "QPushButton:hover { background: #13a10e; }"
            )
            self.ia_status.setText("● Modo anónimo (sin sesión)")
            self.ia_status.setStyleSheet("color: #f7630c; font-weight: bold; font-size: 13px;")
            self.login_msg.setText("")
            return

        email = self.email_input.text().strip()
        password = self.pass_input.text()
        if not email or not password:
            self.login_msg.setText("❌  Ingresa tu email y contraseña.")
            self.login_msg.setStyleSheet("color: #c42b1c; font-size: 12px;")
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("Iniciando sesión...")
        self.login_msg.setText("Conectando con Internet Archive...")
        self.login_msg.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        self._worker = LoginWorker(email, password)
        self._worker.result.connect(self._on_login)
        self._worker.start()

    def _open_web_login(self):
        session = get_session()
        if session.logged_in:
            return
        dlg = WebLoginDialog(self)
        dlg.login_detected.connect(self._on_web_login)
        dlg.exec()

    def _on_web_login(self, username: str):
        self.ia_status.setText(f"● Sesión activa: {username}")
        self.ia_status.setStyleSheet("color: #107c10; font-weight: bold; font-size: 13px;")
        self.login_btn.setText("Cerrar sesión")
        self.login_btn.setStyleSheet(
            "QPushButton { background: #c42b1c; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
            "QPushButton:hover { background: #e81123; }"
        )
        self.login_msg.setText("✅  Sesión iniciada via navegador.")
        self.login_msg.setStyleSheet("color: #107c10; font-size: 12px;")

    def _on_login(self, ok, msg):
        self.login_btn.setEnabled(True)
        if ok:
            self.ia_status.setText(f"● Sesión activa: {get_session().username}")
            self.ia_status.setStyleSheet("color: #107c10; font-weight: bold; font-size: 13px;")
            self.login_btn.setText("Cerrar sesión")
            self.login_btn.setStyleSheet(
                "QPushButton { background: #c42b1c; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
                "QPushButton:hover { background: #e81123; }"
            )
        else:
            self.login_btn.setText("Iniciar sesión")
            self.login_btn.setStyleSheet(
                "QPushButton { background: #107c10; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
                "QPushButton:hover { background: #13a10e; }"
            )
        self.login_msg.setText(("✅  " if ok else "❌  ") + msg)
        self.login_msg.setStyleSheet(f"color: {'#107c10' if ok else '#c42b1c'}; font-size: 12px;")

    def _on_threads_changed(self, v: int):
        dl_module.NUM_THREADS = v
        data = _cfg.load()
        data['num_threads'] = v
        _cfg.save(data)

    def _refresh_session_ui(self):
        """Called on startup — update UI to reflect any restored session."""
        session = get_session()
        if session.logged_in:
            self.ia_status.setText(f"● Sesión activa: {session.username}")
            self.ia_status.setStyleSheet("color: #107c10; font-weight: bold; font-size: 13px;")
            self.login_btn.setText("Cerrar sesión")
            self.login_btn.setStyleSheet(
                "QPushButton { background: #c42b1c; color: white; border: none; border-radius: 6px; padding: 6px 14px; }"
                "QPushButton:hover { background: #e81123; }"
            )
            self.login_msg.setText("✅  Sesión restaurada automáticamente.")
            self.login_msg.setStyleSheet("color: #107c10; font-size: 12px;")
