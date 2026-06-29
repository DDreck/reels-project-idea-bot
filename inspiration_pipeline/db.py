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
    """Connect to or create the work queue database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A configured sqlite3 Connection with Row factory enabled.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def seen_pks(conn: sqlite3.Connection) -> set[str]:
    """Get the set of all primary keys currently in the queue.

    Args:
        conn: Database connection.

    Returns:
        Set of all pk values in the media table.
    """
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


def records_by_status(conn: sqlite3.Connection, status: str
                      ) -> list[sqlite3.Row]:
    """Get all records with a given status, ordered by creation time.

    Args:
        conn: Database connection.
        status: The status value to filter by.

    Returns:
        List of media records with matching status.
    """
    return list(
        conn.execute(
            "SELECT * FROM media WHERE status = ? ORDER BY created_at", (status,)
        )
    )


def mark_transcribed(conn: sqlite3.Connection, pk: str) -> None:
    """Mark a record as transcribed with transcript timestamps.

    Args:
        conn: Database connection.
        pk: Primary key of the record to update.
    """
    now = _now()
    conn.execute(
        "UPDATE media SET status = 'transcribed', transcribed_at = ?, "
        "ocr_at = ?, updated_at = ? WHERE pk = ?",
        (now, now, now, pk),
    )
    conn.commit()


def mark_filed(conn: sqlite3.Connection, pk: str) -> None:
    """Mark a record as filed.

    Args:
        conn: Database connection.
        pk: Primary key of the record to update.
    """
    now = _now()
    conn.execute(
        "UPDATE media SET status = 'filed', filed_at = ?, updated_at = ? "
        "WHERE pk = ?",
        (now, now, pk),
    )
    conn.commit()


def record_failure(
    conn: sqlite3.Connection, pk: str, error: str, max_attempts: int
) -> None:
    """Record a processing failure and increment attempt counter.

    Args:
        conn: Database connection.
        pk: Primary key of the record to update.
        error: Error message describing the failure.
        max_attempts: Maximum allowed attempts before marking as failed.
    """
    row = conn.execute("SELECT attempts FROM media WHERE pk = ?", (pk,)).fetchone()
    attempts = (row["attempts"] if row else 0) + 1
    now = _now()
    if attempts >= max_attempts:
        conn.execute(
            "UPDATE media SET attempts = ?, error = ?, status = 'failed', "
            "updated_at = ? WHERE pk = ?",
            (attempts, error, now, pk),
        )
    else:
        conn.execute(
            "UPDATE media SET attempts = ?, error = ?, updated_at = ? "
            "WHERE pk = ?",
            (attempts, error, now, pk),
        )
    conn.commit()
