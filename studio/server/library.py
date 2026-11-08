"""Drive scanner that builds a searchable library of samples and soundfonts.

Scans user-specified folders (or common sample locations) for audio files and
SoundFonts, indexes them with metadata, and exposes search endpoints.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

AUDIO_EXT = {".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg"}
SOUNDFONT_EXT = {".sf2", ".sfz", ".sf3"}
ALL_EXT = AUDIO_EXT | SOUNDFONT_EXT

DB_PATH = Path.home() / ".nodaw" / "sample_library.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            name TEXT,
            type TEXT,
            size INTEGER,
            mtime REAL,
            duration REAL,
            sample_rate INTEGER,
            channels INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON items(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON items(type)")
    return conn


def scan_paths(paths: list[str], progress_cb: Any = None) -> dict:
    """Scan one or more directories and update the library index."""
    added = 0
    updated = 0
    with _lock:
        conn = _connect()
        for root in paths:
            root_path = Path(root).expanduser().resolve()
            if not root_path.exists():
                continue
            for p in root_path.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in ALL_EXT:
                    continue
                try:
                    stat = p.stat()
                    kind = "soundfont" if p.suffix.lower() in SOUNDFONT_EXT else "sample"
                    # Minimal metadata; full duration requires audio libs (optional)
                    duration = None
                    sr = None
                    ch = None
                    conn.execute(
                        """
                        INSERT INTO items (path, name, type, size, mtime, duration, sample_rate, channels)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            name=excluded.name, size=excluded.size, mtime=excluded.mtime
                        """,
                        (str(p), p.stem, kind, stat.st_size, stat.st_mtime, duration, sr, ch),
                    )
                    added += 1
                except Exception:
                    continue
                if progress_cb and added % 100 == 0:
                    progress_cb(added)
        conn.commit()
        conn.close()
    return {"scanned": added, "db": str(DB_PATH)}


def search(query: str = "", kind: str | None = None, limit: int = 200) -> list[dict]:
    """Search the library by name or path."""
    with _lock:
        conn = _connect()
        sql = "SELECT path, name, type, size, mtime, duration FROM items WHERE 1=1"
        params: list[Any] = []
        if query:
            sql += " AND (name LIKE ? OR path LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like])
        if kind:
            sql += " AND type = ?"
            params.append(kind)
        sql += " ORDER BY name LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def indexed_file(path: str) -> Path | None:
    """Resolve a path only if it is an indexed sample with an audio extension that still exists.
    The file route uses this so it can never read arbitrary files."""
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT path FROM items WHERE path = ? AND type = 'sample'", (path,)).fetchone()
        conn.close()
    if not row:
        return None
    p = Path(row["path"])
    if p.suffix.lower() not in AUDIO_EXT or not p.is_file():
        return None
    return p


def get_stats() -> dict:
    with _lock:
        conn = _connect()
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        samples = conn.execute("SELECT COUNT(*) FROM items WHERE type='sample'").fetchone()[0]
        fonts = conn.execute("SELECT COUNT(*) FROM items WHERE type='soundfont'").fetchone()[0]
        conn.close()
    return {"total": total, "samples": samples, "soundfonts": fonts, "db": str(DB_PATH)}
