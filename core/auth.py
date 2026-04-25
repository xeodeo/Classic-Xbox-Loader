"""
Internet Archive authentication module.
Supports login with email/password or anonymous access.
"""
import re
import sys
import os
import json
import requests
import logging

logger = logging.getLogger(__name__)

IA_LOGIN_URL = "https://archive.org/account/login"


def _session_file_path() -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    return os.path.join(base, 'ia_session.json')


class IASession:
    """Manages an authenticated or anonymous session with Internet Archive."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
        })
        self.logged_in = False
        self.username = None
        self._try_load_session()

    def login(self, email: str, password: str) -> tuple:
        """Login to Internet Archive. Returns (success: bool, message: str)"""
        try:
            # Step 1: GET login page to collect cookies + any hidden CSRF fields
            page = self.session.get(IA_LOGIN_URL, timeout=15)
            page.raise_for_status()

            # Extract any hidden form fields (CSRF tokens, etc.)
            hidden = {}
            for m in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', page.text, re.I):
                name_m = re.search(r'name=["\']([^"\']+)["\']', m.group())
                val_m = re.search(r'value=["\']([^"\']*)["\']', m.group())
                if name_m and val_m:
                    hidden[name_m.group(1)] = val_m.group(1)

            payload = {
                **hidden,
                'username': email,
                'password': password,
                'remember': 'CHECKED',
                'referer': 'https://archive.org',
                'login': 'true',
                'submit_by_js': 'true',
            }
            resp = self.session.post(
                IA_LOGIN_URL, data=payload, timeout=15, allow_redirects=True,
                headers={'Referer': IA_LOGIN_URL}
            )

            if 'logged-in-user' in self.session.cookies or 'logged-in-sig' in self.session.cookies:
                self.logged_in = True
                self.username = self.session.cookies.get('logged-in-user', email)
                self.save_session()
                return True, f"Sesion iniciada como {self.username}"

            # Fallback: verify via the whoami API
            check = self.session.get('https://archive.org/account/index.php?output=json', timeout=10)
            if check.ok:
                try:
                    data = check.json()
                    if data.get('username'):
                        self.logged_in = True
                        self.username = data['username']
                        self.save_session()
                        return True, f"Sesion iniciada como {self.username}"
                except Exception:
                    pass

            return False, "Credenciales incorrectas o metodo de login no compatible. Usa el boton 'Login con Google / Navegador'."
        except requests.exceptions.ConnectionError:
            return False, "Error de conexion. Verifica tu internet."
        except requests.exceptions.Timeout:
            return False, "Tiempo de espera agotado."
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, f"Error: {str(e)}"

    def save_session(self):
        """Persist cookies to disk so the user stays logged in across restarts."""
        try:
            data = {
                'logged_in': self.logged_in,
                'username': self.username,
                'cookies': {k: v for k, v in self.session.cookies.items()},
            }
            with open(_session_file_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Could not save session: {e}")

    def _try_load_session(self):
        """Load saved cookies from disk and restore the session immediately.
        Verifies with IA only to detect explicit expiry — network errors are
        ignored so the session survives offline starts or slow connections.
        """
        try:
            path = _session_file_path()
            if not os.path.exists(path):
                return
            with open(path, encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                return
            data = json.loads(content)
            if not data.get('logged_in') or not data.get('cookies'):
                return
            # Restore session immediately from saved data
            self.session.cookies.update(data['cookies'])
            self.logged_in = True
            self.username = data.get('username', '')
            logger.info(f"Session loaded from disk for {self.username}")
        except Exception as e:
            logger.warning(f"Could not load session: {e}")
            return

        # Verify silently — only clear if IA explicitly says session is invalid
        try:
            resp = self.session.get(
                'https://archive.org/account/index.php?output=json', timeout=10
            )
            if resp.ok:
                try:
                    info = resp.json()
                    if info.get('username'):
                        self.username = info['username']
                        self.save_session()
                        logger.info(f"Session verified for {self.username}")
                        return
                except Exception:
                    pass
                # IA returned non-JSON (HTML login page) — session expired
                self.session.cookies.clear()
                self.logged_in = False
                self.username = None
                logger.info("Session expired, cleared.")
            # Non-ok HTTP but not a network error — keep session as-is
        except Exception:
            # Network error (timeout, offline, etc.) — keep the restored session
            logger.info("Could not verify session (network error) — keeping saved session.")

    def logout(self):
        self.session.cookies.clear()
        self.logged_in = False
        self.username = None
        try:
            p = _session_file_path()
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    def get(self, url, **kwargs):
        return self.session.get(url, **kwargs)

    def head(self, url, **kwargs):
        return self.session.head(url, **kwargs)

    def get_session(self) -> requests.Session:
        return self.session


_ia_session = IASession()


def get_session() -> IASession:
    return _ia_session
