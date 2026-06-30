"""Cut a short clip from a saved reel video with ffmpeg.

Given a reel shortcode and a start/end (``m:ss`` or seconds), trims the saved
``<output_dir>/_videos/<shortcode>.mp4`` to ``<output_dir>/_clips/<name>.mp4``
and prints the clip path. Intended to be called by OpenClaw when it wants to
send the relevant moment of a reel (e.g. an exercise demo) over Telegram.

Usage:
    python tools/clip.py <shortcode> <start> <end> [--config config.toml]
    python tools/clip.py DT5i-QgjgrT 0:05 0:18
"""
import argparse
import subprocess
import sys
from pathlib import Path

from inspiration_pipeline.config import load_config


def _parse_time(value: str) -> float:
    """Parse ``m:ss``, ``h:mm:ss``, or plain seconds into float seconds."""
    parts = value.split(":")
    if len(parts) == 1:
        return float(parts[0])
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def make_clip(output_dir: Path, shortcode: str, start: float, end: float,
              *, runner=subprocess.run) -> Path:
    """Trim the reel video to [start, end] and return the clip path."""
    source = output_dir / "_videos" / f"{shortcode}.mp4"
    if not source.exists():
        raise FileNotFoundError(f"No saved video for {shortcode}: {source}")
    if end <= start:
        raise ValueError(f"end ({end}) must be after start ({start})")
    clips_dir = output_dir / "_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    out = clips_dir / f"{shortcode}_{int(start)}-{int(end)}.mp4"
    # Accurate seek (decode from start) -- reels are short, so this is fast and
    # frame-accurate, which matters for "show me how to do the move" clips.
    runner(
        ["ffmpeg", "-y", "-i", str(source), "-ss", str(start), "-to", str(end),
         "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True, text=True,
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clip a reel video.")
    parser.add_argument("shortcode")
    parser.add_argument("start", help="start time (m:ss or seconds)")
    parser.add_argument("end", help="end time (m:ss or seconds)")
    parser.add_argument("--config", default="config.toml", type=Path)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    clip = make_clip(cfg.output_dir, args.shortcode,
                     _parse_time(args.start), _parse_time(args.end))
    print(clip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
