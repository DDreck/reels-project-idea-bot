"""sqlite-backed work queue for reels."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from inspiration_pipeline.models import ReelMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    pk TEXT PRIMARY KEY,
    shortcode TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT NOT NULL,
    caption TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    collection TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'downloaded',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    downloaded_at TEXT,
    transcribed_at TEXT,
    ocr_at TEXT,
    filed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def seen_pks(conn: sqlite3.Connection) -> set[str]:
    return {row["pk"] for row in conn.execute("SELECT pk FROM media")}


def enqueue(conn: sqlite3.Connection, reel: ReelMeta) -> bool:
    """Insert a downloaded reel. Returns False if pk already exists."""
    now = _now()
    try:
        conn.execute(
            "INSERT INTO media (pk, shortcode, url, author, caption, taken_at,"
            " collection, status, downloaded_at, created_at, updated_at) VALUES"
            " (?,?,?,?,?,?,?, 'downloaded', ?, ?, ?)",
            (reel.pk, reel.shortcode, reel.url, reel.author, reel.caption,
             reel.taken_at, reel.collection, now, now, now),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def records_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM media WHERE status = ? ORDER BY created_at", (status,)
        )
    )


def _set(conn: sqlite3.Connection, pk: str, assignments: str, params: tuple) -> None:
    conn.execute(
        f"UPDATE media SET {assignments}, updated_at = ? WHERE pk = ?",
        (*params, _now(), pk),
    )
    conn.commit()


def mark_transcribed(conn: sqlite3.Connection, pk: str) -> None:
    now = _now()
    _set(conn, pk, "status='transcribed', transcribed_at=?, ocr_at=?", (now, now))


def mark_filed(conn: sqlite3.Connection, pk: str) -> None:
    _set(conn, pk, "status='filed', filed_at=?", (_now(),))


def record_failure(
    conn: sqlite3.Connection, pk: str, error: str, max_attempts: int
) -> None:
    row = conn.execute("SELECT attempts FROM media WHERE pk = ?", (pk,)).fetchone()
    attempts = (row["attempts"] if row else 0) + 1
    status = "failed" if attempts >= max_attempts else None
    if status:
        _set(conn, pk, "attempts=?, error=?, status='failed'", (attempts, error))
    else:
        _set(conn, pk, "attempts=?, error=?", (attempts, error))
