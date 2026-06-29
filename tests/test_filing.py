from pathlib import Path

from inspiration_pipeline import db, filing
from inspiration_pipeline.models import Classification, ReelMeta


def _reel(pk="1"):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url="u", author="@a",
                    caption="cap", taken_at="2026-06-25", collection="3d prints")


def _classifier(cls):
    def fn(config, reel, transcript, ocr, categories, **kw):
        return cls
    return fn


def test_file_reel_writes_note_purges_video_marks_filed(tmp_path, dummy_config):
    config = dummy_config
    config.output_dir.mkdir(parents=True)
    conn = db.connect(config.db_path)
    db.enqueue(conn, _reel())
    db.mark_transcribed(conn, "1")
    video = tmp_path / "1.mp4"
    video.write_bytes(b"x")
    cls = Classification("3d-print", "Hinge", "s", ["p"], "Projects",
                         is_new_category=True, category_description="prints")
    note_path = filing.file_reel(conn, config, _reel(), "trans", "ocr",
                                 video_path=video, classifier=_classifier(cls))
    assert note_path.exists()
    assert "[[Projects]]" in note_path.read_text(encoding="utf-8")
    assert not video.exists()  # purged
    assert db.records_by_status(conn, "filed")[0]["pk"] == "1"
    cats = (config.output_dir / "_categories.md").read_text(encoding="utf-8")
    assert "3d-print" in cats  # new category registered


def test_file_reel_keep_originals(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "keep_originals", True)
    config.output_dir.mkdir(parents=True)
    conn = db.connect(config.db_path)
    db.enqueue(conn, _reel())
    db.mark_transcribed(conn, "1")
    video = tmp_path / "1.mp4"
    video.write_bytes(b"x")
    cls = Classification("workout", "W", "s", [], "Health")
    filing.file_reel(conn, config, _reel(), "t", "o", video_path=video,
                     classifier=_classifier(cls))
    assert video.exists()  # kept
    assert db.records_by_status(conn, "filed")[0]["pk"] == "1"
