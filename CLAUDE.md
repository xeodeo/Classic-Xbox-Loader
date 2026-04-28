# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run (dev mode):**
```
python main.py
```

**Install dependencies:**
```
pip install -r requirements.txt
```

**Build distributable (Windows only):**
```
build_app.bat
```
Output: `dist/ClassicXboxLoader/ClassicXboxLoader.exe`

There are no automated tests in this project.

## Architecture

Classic Xbox Loader is a PyQt6 desktop app that downloads classic Xbox game ISOs from Internet Archive, extracts them, and installs them to a modded Xbox via FTP.

### Layout

- `main.py` — entry point; creates `QApplication`, applies global dark stylesheet, launches `MainWindow`
- `ui/main_window.py` — sidebar + `QStackedWidget` with 5 panels; `DOWNLOADS_DIR` is resolved here relative to the exe/source root
- `ui/styles.py` — single `DARK_STYLE` string applied globally via `app.setStyleSheet()`
- `core/config.py` — reads/writes `settings.json` next to the exe (or project root in dev mode)

### Panels (ui/)

| Panel | Purpose |
|---|---|
| `catalog_panel.py` | Browse games by letter, fetch metadata from Internet Archive API |
| `downloads_panel.py` | Manage in-progress and completed downloads |
| `install_panel.py` | Select a downloaded ZIP/ISO, extract it, upload to Xbox |
| `ftp_panel.py` | File browser for the Xbox over FTP (upload/download/navigate) |
| `settings_panel.py` | FTP credentials, Internet Archive login, preferences (uses `QWebEngineView`) |

### Core modules

- `core/catalog.py` — fetches game lists from `archive.org` metadata API; `COLLECTION_MAP` maps A-Z letters to archive item identifiers; only `.zip` files are returned
- `core/downloader.py` — `QThread`-based download worker with resume support
- `core/extractor.py` — `ExtractWorker(QThread)` extracts ZIP files with chunked byte-level progress signals
- `core/xiso_processor.py` — `XisoWorker(QThread)` wraps `extract-xiso.exe -x <iso>` to unpack Xbox ISOs; the exe lives in `extract iso a xiso/` and is located via `get_xiso_path()` which checks both `sys._MEIPASS` and `os.path.dirname(sys.executable)` for PyInstaller onedir compatibility
- `core/ftp_client.py` — `FTPClient` wraps `ftplib.FTP`; uses CWD + relative STOR (Xbox FTP servers reject absolute paths); RLock serializes all calls; TCP keepalive prevents WinError 10053 on long transfers; `_PARTITION_MAP` normalizes Xbox drive names (e, hdd0-e, etc.) to `E:` style
- `core/auth.py` — Internet Archive session/cookie management

### Threading pattern

All long operations run in `QThread` subclasses that emit `pyqtSignal`s for progress, completion, and errors. Workers are owned by their panel widgets. Never call Qt UI methods directly from worker threads — use signals only.

### PyInstaller notes

- `QtWebEngineWidgets` **must** be imported before `QApplication` is created (done in `main.py`)
- The `extract iso a xiso/` folder is added via `--add-data` in `build_app.bat`
- `get_app_dir()` / `get_xiso_path()` functions handle both frozen and dev-mode paths

### Settings persistence

`core/config.py` stores a flat JSON dict in `settings.json`. Load with `config.load()`, mutate, save with `config.save(cfg)`. Used for FTP credentials, IA login cookies, and UI preferences (`hide_welcome`, etc.).
