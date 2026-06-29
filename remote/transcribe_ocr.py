"""Runs ON dreck (RTX 5090). Transcribe + OCR each mp4 in a dir to <stem>.json."""
import argparse
import json
import sys
from pathlib import Path


def dedup_lines(lines: list[str]) -> str:
    """Join non-empty lines, removing duplicates while preserving order.

    Args:
        lines: Raw text lines, possibly repeated or blank.

    Returns:
        Newline-joined string with unique, non-blank lines.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        text = line.strip()
        if text and text not in seen:
            seen.add(text)
            kept.append(text)
    return "\n".join(kept)


def _whisper_transcribe(model_name: str):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cuda", compute_type="float16")

    def transcribe(path: Path) -> str:
        segments, _ = model.transcribe(str(path))
        return " ".join(seg.text.strip() for seg in segments).strip()

    return transcribe


def _frame_ocr(fps: float = 1.0):
    import cv2
    import pytesseract

    def ocr(path: Path) -> list[str]:
        cap = cv2.VideoCapture(str(path))
        native = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(int(native / fps), 1)
        lines: list[str] = []
        idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % step == 0:
                    text = pytesseract.image_to_string(frame)
                    lines.extend(text.splitlines())
                idx += 1
        finally:
            cap.release()
        return lines

    return ocr


def process_video(path: Path, transcriber, ocr_fn) -> dict:
    """Transcribe and OCR a single video file.

    Args:
        path: Path to the mp4 video.
        transcriber: Callable ``(path) -> str`` for speech-to-text.
        ocr_fn: Callable ``(path) -> list[str]`` for frame OCR.

    Returns:
        Dict with keys ``transcript`` (str) and ``ocr`` (str).
    """
    return {"transcript": transcriber(path), "ocr": dedup_lines(ocr_fn(path))}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scratch_dir")
    parser.add_argument("--model", default="large-v3")
    args = parser.parse_args(argv)
    transcriber = _whisper_transcribe(args.model)
    ocr_fn = _frame_ocr()
    scratch = Path(args.scratch_dir)
    for video in scratch.glob("*.mp4"):
        result = process_video(video, transcriber, ocr_fn)
        (scratch / f"{video.stem}.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
        video.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
