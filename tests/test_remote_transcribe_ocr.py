import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "transcribe_ocr", Path(__file__).parent.parent / "remote" / "transcribe_ocr.py"
)
tx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tx)


def test_dedup_lines_preserves_order_drops_repeats():
    assert tx.dedup_lines(["a", "a", "b", "", "b", "c"]) == "a\nb\nc"


def test_process_video_combines_transcript_and_ocr(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    result = tx.process_video(
        video, transcriber=lambda p: "spoken text",
        ocr_fn=lambda p: ["LINE ONE", "LINE ONE", "LINE TWO"],
    )
    assert result == {"transcript": "spoken text", "ocr": "LINE ONE\nLINE TWO"}
