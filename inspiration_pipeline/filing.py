"""Classify, render, write, and finalize one transcribed reel."""
from datetime import date
from pathlib import Path

from inspiration_pipeline import categories, claude_client, db, notes
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


def _place_keyframes(output_dir: Path, src_dir: Path, names) -> list[str]:
    """Move keyframe images into the vault's _frames dir; return placed names."""
    if not names:
        return []
    frames_dir = output_dir / "_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    placed: list[str] = []
    for name in names:
        src = src_dir / name
        if src.exists():
            (frames_dir / name).write_bytes(src.read_bytes())
            src.unlink()
            placed.append(name)
    return placed


def file_reel(
    conn,
    config: Config,
    reel: ReelMeta,
    transcript: str,
    ocr: str,
    *,
    video_path: Path,
    keyframes=(),
    classifier=claude_client.classify_reel,
) -> Path:
    """Turn a transcribed reel into a filed vault note. Returns the note path."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    registry = config.output_dir / "_categories.md"
    known = categories.read_categories(registry)
    cls = classifier(config, reel, transcript, ocr, known)
    if cls.is_new_category:
        categories.append_category(registry, cls.category, cls.category_description)
    frames = _place_keyframes(config.output_dir, video_path.parent, keyframes)
    note = notes.render_note(
        reel, transcript, ocr, cls, date.today().isoformat(), keyframes=frames
    )
    note_path = config.output_dir / notes.note_filename(reel)
    note_path.write_text(note, encoding="utf-8")
    if not config.keep_originals and video_path.exists():
        video_path.unlink()
    db.mark_filed(conn, reel.pk)
    return note_path
