"""Runs ON dreck (RTX 5090). Transcribe + OCR + keyframe each mp4 to <stem>.json."""
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


def _ensure_cuda_dlls() -> None:
    """On Windows, add the pip nvidia cuBLAS/cuDNN bin dirs to the DLL path.

    ctranslate2 (faster-whisper's backend) needs cublas64_12.dll / cudnn at
    runtime; the Windows wheels don't bundle them, so they come from the
    ``nvidia-cublas-cu12`` / ``nvidia-cudnn-cu12`` packages. No-op elsewhere.
    """
    import importlib.util
    import os
    import sys

    if not sys.platform.startswith("win"):
        return
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except Exception:  # noqa: BLE001 - best-effort DLL discovery
            spec = None
        if not spec or not spec.submodule_search_locations:
            continue
        for loc in spec.submodule_search_locations:
            dll_dir = Path(loc) / "bin"
            if dll_dir.is_dir():
                os.add_dll_directory(str(dll_dir))
                # ctranslate2 loads cuBLAS via legacy LoadLibrary, which
                # searches PATH (not add_dll_directory dirs) -- prepend it too.
                os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ["PATH"]


def _whisper_transcribe(model_name: str):
    _ensure_cuda_dlls()
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cuda", compute_type="float16")

    def transcribe(path: Path) -> str:
        # vad_filter drops music/silence segments (the main source of
        # hallucinated text on reels); beam search + no prev-text conditioning
        # improve accuracy and avoid repetition loops over backing tracks.
        segments, _ = model.transcribe(
            str(path), beam_size=5, vad_filter=True,
            condition_on_previous_text=False,
        )
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


def _keyframes(path: Path, count: int = 4) -> list[Path]:
    """Save ``count`` evenly-spaced JPEG keyframes next to the video.

    Args:
        path: Path to the mp4 video.
        count: Number of frames to extract (spread across the clip).

    Returns:
        Paths of the saved ``<stem>_f{i}.jpg`` files.
    """
    import cv2

    cap = cv2.VideoCapture(str(path))
    saved: list[Path] = []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        if total <= 0:
            return saved
        positions = [int(total * (i + 1) / (count + 1)) for i in range(count)]
        for i, pos in enumerate(positions):
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok:
                continue
            out = path.parent / f"{path.stem}_f{i}.jpg"
            cv2.imwrite(str(out), frame)
            saved.append(out)
    finally:
        cap.release()
    return saved


def process_video(path: Path, transcriber, ocr_fn, keyframe_fn) -> dict:
    """Transcribe, OCR, and extract keyframes for a single video.

    Args:
        path: Path to the mp4 video.
        transcriber: Callable ``(path) -> str`` for speech-to-text.
        ocr_fn: Callable ``(path) -> list[str]`` for frame OCR.
        keyframe_fn: Callable ``(path) -> list[Path]`` saving keyframe images.

    Returns:
        Dict with keys ``transcript`` (str), ``ocr`` (str), and ``keyframes``
        (list of saved image filenames).
    """
    frames = [p.name for p in keyframe_fn(path)]
    return {
        "transcript": transcriber(path),
        "ocr": dedup_lines(ocr_fn(path)),
        "keyframes": frames,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scratch_dir")
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--frames", type=int, default=4)
    args = parser.parse_args(argv)
    transcriber = _whisper_transcribe(args.model)
    ocr_fn = _frame_ocr()
    scratch = Path(args.scratch_dir)
    for video in scratch.glob("*.mp4"):
        result = process_video(
            video, transcriber, ocr_fn, lambda p: _keyframes(p, args.frames)
        )
        (scratch / f"{video.stem}.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
        video.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
