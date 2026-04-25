"""
Fetches game catalog from Internet Archive metadata API.
Each letter maps to one or more archive.org item identifiers.
"""
import logging
import requests
from core.auth import get_session

logger = logging.getLogger(__name__)

COLLECTION_MAP = {
    '#': ['microsoft_xbox_numberssymbols'],
    'A': ['microsoft_xbox_a'],
    'B': ['microsoft_xbox_b'],
    'C': ['microsoft_xbox_c_part1', 'microsoft_xbox_c_part2'],
    'D': ['microsoft_xbox_d_part1', 'microsoft_xbox_d_part2'],
    'E': ['microsoft_xbox_e'],
    'F': ['microsoft_xbox_f'],
    'G': ['microsoft_xbox_g'],
    'H': ['microsoft_xbox_h'],
    'I': ['microsoft_xbox_i'],
    'J': ['microsoft_xbox_j'],
    'K': ['microsoft_xbox_k'],
    'L': ['microsoft_xbox_l'],
    'M': ['microsoft_xbox_m_part1', 'microsoft_xbox_m_part2'],
    'N': ['microsoft_xbox_n_part1', 'microsoft_xbox_n_part2'],
    'O': ['microsoft_xbox_o_part1', 'microsoft_xbox_o_part2'],
    'P': ['microsoft_xbox_p'],
    'Q': ['microsoft_xbox_q'],
    'R': ['microsoft_xbox_r'],
    'S': ['microsoft_xbox_s_part1', 'microsoft_xbox_s_part2'],
    'T': ['microsoft_xbox_t_part1', 'microsoft_xbox_t_part2'],
    'U': ['microsoft_xbox_u'],
    'V': ['microsoft_xbox_v'],
    'W': ['microsoft_xbox_w'],
    'X': ['microsoft_xbox_x'],
    'Y': ['microsoft_xbox_y'],
    'Z': ['microsoft_xbox_z'],
}

ALL_LETTERS = ['#'] + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def fetch_letter(letter: str, progress_callback=None) -> list:
    """
    Fetch all games for a given letter from Archive.org metadata API.
    Returns list of dicts with name, display_name, size, size_str, url, identifier.
    Only returns .zip files.
    """
    identifiers = COLLECTION_MAP.get(letter.upper(), [])
    games = []
    session = get_session().get_session()

    for identifier in identifiers:
        if progress_callback:
            progress_callback(f"Cargando {identifier}...")
        try:
            url = f"https://archive.org/metadata/{identifier}"
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for f in data.get('files', []):
                name = f.get('name', '')
                if not name.lower().endswith('.zip'):
                    continue
                if name.startswith('_') or name.endswith('.xml') or name.endswith('.sqlite'):
                    continue
                size = int(f.get('size', 0))
                download_url = (
                    f"https://archive.org/download/{identifier}/"
                    f"{requests.utils.quote(name)}"
                )
                display_name = name[:-4] if name.endswith('.zip') else name
                games.append({
                    'name': name,
                    'display_name': display_name,
                    'size': size,
                    'size_str': format_size(size),
                    'url': download_url,
                    'identifier': identifier,
                    'letter': letter,
                })
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {identifier}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for {identifier}: {e}")

    return sorted(games, key=lambda x: x['display_name'].lower())


def search_games(games: list, query: str) -> list:
    """Filter games list by search query (case-insensitive)."""
    q = query.lower().strip()
    if not q:
        return games
    return [g for g in games if q in g['display_name'].lower()]
