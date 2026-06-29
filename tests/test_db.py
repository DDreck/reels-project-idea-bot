from inspiration_pipeline import db
from inspiration_pipeline.models import ReelMeta


def _reel(pk="1"):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url=f"http://x/{pk}",
                    author="@a", caption="cap", taken_at="2026-06-25",
                    collection="projects")


def test_enqueue_and_dedup(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert db.enqueue(conn, _reel("1")) is True
    assert db.enqueue(conn, _reel("1")) is False  # duplicate pk
    assert db.seen_pks(conn) == {"1"}


def test_status_transitions_set_timestamps(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.enqueue(conn, _reel("1"))
    assert [r["pk"] for r in db.records_by_status(conn, "downloaded")] == ["1"]
    db.mark_transcribed(conn, "1")
    row = db.records_by_status(conn, "transcribed")[0]
    assert row["transcribed_at"] is not None and row["ocr_at"] is not None
    db.mark_filed(conn, "1")
    row = db.records_by_status(conn, "filed")[0]
    assert row["filed_at"] is not None


def test_record_failure_marks_failed_at_max(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.enqueue(conn, _reel("1"))
    db.record_failure(conn, "1", "boom", max_attempts=2)
    assert db.records_by_status(conn, "failed") == []  # attempts=1 < 2
    db.record_failure(conn, "1", "boom", max_attempts=2)
    failed = db.records_by_status(conn, "failed")
    assert len(failed) == 1 and failed[0]["attempts"] == 2
    assert failed[0]["error"] == "boom"
