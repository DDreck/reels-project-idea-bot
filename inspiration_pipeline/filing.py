"""Classify, render, write, and finalize one transcribed reel."""
from datetime import date
from pathlib import Path

from inspiration_pipeline import categories, claude_client, db, notes
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


def file_reel(
    conn,
    config: Config,
    reel: ReelMeta,
    transcript: str,
    ocr: str,
    video_path: Path,
    *,
    classifier=claude_client.classify_reel,
) -> Path:
    """Turn a transcribed reel into a filed vault note. Returns the note path."""
    registry = config.output_dir / "_categories.md"
    known = categories.read_categories(registry)
    cls = classifier(config, reel, transcript, ocr, known)
    if cls.is_new_category:
        categories.append_category(registry, cls.category, cls.category_description)
    note = notes.render_note(reel, transcript, ocr, cls, date.today().isoformat())
    config.output_dir.mkdir(parents=True, exist_ok=True)
    note_path = config.output_dir / notes.note_filename(reel)
    note_path.write_text(note, encoding="utf-8")
    if not config.keep_originals and video_path.exists():
        video_path.unlink()
    db.mark_filed(conn, reel.pk)
    return note_path
