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


def _place_video(output_dir: Path, video_path: Path) -> str | None:
    """Move the reel video into the vault's _videos dir; return its filename."""
    if not video_path.exists():
        return None
    videos_dir = output_dir / "_videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    dest = videos_dir / video_path.name
    dest.write_bytes(video_path.read_bytes())
    video_path.unlink()
    return video_path.name


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
    if config.keep_originals:
        video_name = _place_video(config.output_dir, video_path)
    else:
        video_name = None
        if video_path.exists():
            video_path.unlink()
    note = notes.render_note(
        reel, transcript, ocr, cls, date.today().isoformat(),
        keyframes=frames, video=video_name,
    )
    note_path = config.output_dir / notes.note_filename(reel)
    note_path.write_text(note, encoding="utf-8")
    db.mark_filed(conn, reel.pk)
    return note_path
