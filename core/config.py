"""Simple persistent settings stored in settings.json next to the executable."""
import os
import sys
import json


def _path() -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    return os.path.join(base, 'settings.json')


def load() -> dict:
    try:
        with open(_path(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save(data: dict):
    try:
        with open(_path(), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
