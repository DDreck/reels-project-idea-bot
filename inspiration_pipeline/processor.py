"""Batch processor: wake dreck, transcribe, file reels."""
import json
from pathlib import Path

from inspiration_pipeline import db, dreck as dreck_default, filing
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


def _reel_from_row(row) -> ReelMeta:
    return ReelMeta(
        pk=row["pk"], shortcode=row["shortcode"], url=row["url"],
        author=row["author"], caption=row["caption"],
        taken_at=row["taken_at"], collection=row["collection"],
    )


def process(conn, config: Config, *, dreck_mod=dreck_default,
            file_fn=filing.file_reel, classifier=None) -> int:
    """Transcribe + file up to batch_size queued reels. Returns count filed."""
    rows = db.records_by_status(conn, "downloaded")[: config.batch_size]
    if not rows:
        return 0
    dreck_mod.wake(config)
    if not dreck_mod.wait_for_ssh(config):
        return 0  # leave everything queued; retry next batch
    videos = [config.queue_dir / f"{r['shortcode']}.mp4" for r in rows]
    try:
        dreck_mod.push(config, [v for v in videos if v.exists()])
        dreck_mod.run_transcription(config)
        dreck_mod.pull_results(config, config.queue_dir)
        dreck_mod.clear_scratch(config)
    finally:
        dreck_mod.sleep_host(config)
    filed = 0
    for row in rows:
        reel = _reel_from_row(row)
        try:
            result = _load_result(config.queue_dir / f"{reel.shortcode}.json")
            db.mark_transcribed(conn, reel.pk)
            kwargs = {"classifier": classifier} if classifier else {}
            file_fn(conn, config, reel, result["transcript"], result["ocr"],
                    video_path=config.queue_dir / f"{reel.shortcode}.mp4", **kwargs)
            filed += 1
        except Exception as exc:  # noqa: BLE001 - per-reel isolation
            db.record_failure(conn, reel.pk, str(exc), config.max_attempts)
    return filed


def _load_result(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
