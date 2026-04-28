"""
Pure-Python Xbox ISO (XDVDFS) extractor.
Implements the same extraction logic as extract-xiso -x without any external executable.
"""
import os
import struct
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# ── XDVDFS constants (from extract-xiso.c) ──────────────────────────────────
SECTOR_SIZE      = 2048
MAGIC            = b"MICROSOFT*XBOX*MEDIA"
HEADER_OFFSET    = 0x10000   # volume descriptor is always at lseek_offset + 0x10000
ATTR_DIR         = 0x10
PAD_SHORT        = 0xFFFF

# lseek_offset per disc type (added to every sector seek, and to HEADER_OFFSET)
LSEEK_OFFSETS = [
    0x00000000,   # Standard ripped ISO
    0x18300000,   # XGD1 – original Xbox retail disc
    0x0FD90000,   # XGD2 – Xbox 360
    0x02080000,   # XGD3 – Xbox 360 latest
]

READ_CHUNK = 256 * 1024   # 256 KB per I/O during file extraction


# ── Low-level helpers ────────────────────────────────────────────────────────

def _find_volume_descriptor(f):
    """
    Try each known lseek_offset.  Volume descriptor lives at lseek_offset + 0x10000.
    Returns (lseek_offset, root_sector, root_size) or raises ValueError.
    """
    tail_off = SECTOR_SIZE - len(MAGIC)   # 2028 = 0x7EC  (last 20 bytes of sector)

    for lseek_offset in LSEEK_OFFSETS:
        try:
            f.seek(lseek_offset + HEADER_OFFSET)
            hdr = f.read(SECTOR_SIZE)
        except OSError:
            continue
        if len(hdr) < SECTOR_SIZE:
            continue
        if hdr[:len(MAGIC)] == MAGIC and hdr[tail_off:tail_off + len(MAGIC)] == MAGIC:
            root_sector = struct.unpack_from('<I', hdr, 20)[0]
            root_size   = struct.unpack_from('<I', hdr, 24)[0]
            return lseek_offset, root_sector, root_size

    raise ValueError(
        "No se encontró un volumen XDVDFS válido en el ISO.\n"
        "Asegúrate de que el archivo sea un Xbox ISO (.iso) válido."
    )


def _read_dir_table(f, lseek_offset, dir_sector, dir_size):
    """Read all sectors that make up a directory table into a bytearray."""
    n_sectors = max(1, (dir_size + SECTOR_SIZE - 1) // SECTOR_SIZE)
    data = bytearray()
    for i in range(n_sectors):
        pos = lseek_offset + (dir_sector + i) * SECTOR_SIZE
        f.seek(pos)
        chunk = f.read(SECTOR_SIZE)
        if not chunk:
            break
        data.extend(chunk)
    return data


def _iter_dir_entries(data):
    """
    Walk the XDVDFS directory binary-tree stored in *data*.
    Entry offsets are in 4-byte units from the start of the directory table.
    Yields (name, is_dir, sector, size) using an explicit stack (no recursion).
    """
    stack = [0]
    visited = set()
    while stack:
        offset_units = stack.pop()
        if offset_units == PAD_SHORT or offset_units in visited:
            continue
        visited.add(offset_units)

        byte_off = offset_units * 4
        if byte_off + 14 > len(data):
            continue

        left        = struct.unpack_from('<H', data, byte_off)[0]
        right       = struct.unpack_from('<H', data, byte_off + 2)[0]
        file_sector = struct.unpack_from('<I', data, byte_off + 4)[0]
        file_size   = struct.unpack_from('<I', data, byte_off + 8)[0]
        attributes  = data[byte_off + 12]
        name_len    = data[byte_off + 13]

        if name_len == 0 or byte_off + 14 + name_len > len(data):
            continue

        raw_name = data[byte_off + 14: byte_off + 14 + name_len]
        # Reject entries whose name contains null bytes (corrupt / padding)
        if b'\x00' in raw_name:
            continue
        name   = raw_name.decode('latin-1', errors='replace')
        is_dir = bool(attributes & ATTR_DIR)

        yield name, is_dir, file_sector, file_size

        if left  != PAD_SHORT:
            stack.append(left)
        if right != PAD_SHORT:
            stack.append(right)


# ── Public extraction function ───────────────────────────────────────────────

def extract_xiso(iso_path, dest_dir, progress_cb=None):
    """
    Extract an Xbox ISO (XDVDFS) to *dest_dir*.
    progress_cb(str) called per extracted file.
    Returns total files extracted.  Raises on failure.
    """
    with open(iso_path, 'rb') as f:
        lseek_offset, root_sector, root_size = _find_volume_descriptor(f)

        os.makedirs(dest_dir, exist_ok=True)

        total_files = 0
        # Stack entries: (dir_sector, dir_size, output_path)
        dir_stack = [(root_sector, root_size, dest_dir)]

        while dir_stack:
            dir_sector, dir_size, out_path = dir_stack.pop()
            os.makedirs(out_path, exist_ok=True)

            dir_data = _read_dir_table(f, lseek_offset, dir_sector, dir_size)

            for name, is_dir, sector, size in _iter_dir_entries(dir_data):
                child_path = os.path.join(out_path, name)

                if is_dir:
                    dir_stack.append((sector, size, child_path))
                else:
                    parent = os.path.dirname(child_path)
                    if parent:
                        os.makedirs(parent, exist_ok=True)

                    f.seek(lseek_offset + sector * SECTOR_SIZE)
                    remaining = size
                    with open(child_path, 'wb') as out_f:
                        while remaining > 0:
                            chunk = f.read(min(remaining, READ_CHUNK))
                            if not chunk:
                                break
                            out_f.write(chunk)
                            remaining -= len(chunk)

                    total_files += 1
                    rel = os.path.relpath(child_path, dest_dir)
                    if progress_cb:
                        progress_cb(f"[{total_files}] {rel}")

    return total_files


# ── QThread worker (same interface as before) ────────────────────────────────

class XisoWorker(QThread):
    """Extracts an Xbox ISO in a background thread using the built-in Python extractor."""
    output_line = pyqtSignal(str)
    finished    = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(self, iso_path: str, parent=None):
        super().__init__(parent)
        self.iso_path = iso_path

    def run(self):
        if not os.path.exists(self.iso_path):
            self.error.emit(f"ISO no encontrada: {self.iso_path}")
            return

        work_dir = os.path.dirname(self.iso_path)
        iso_name = os.path.splitext(os.path.basename(self.iso_path))[0]
        dest_dir = os.path.join(work_dir, iso_name)

        try:
            count = extract_xiso(
                self.iso_path,
                dest_dir,
                progress_cb=self.output_line.emit,
            )
            self.output_line.emit(f"Extracción completada: {count} archivos.")
            self.finished.emit(dest_dir)
        except Exception as e:
            logger.error(f"xiso extract error: {e}")
            self.error.emit(str(e))
