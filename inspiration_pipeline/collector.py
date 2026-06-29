"""Poll Instagram collections, download new reels, enqueue them."""
import subprocess
from pathlib import Path

from inspiration_pipeline import db
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


class InstagramSource:
    """instagrapi wrapper. The only module that imports instagrapi."""

    def __init__(self, config: Config) -> None:
        from instagrapi import Client

        self._config = config
        self._client = Client()

    def login(self) -> None:
        cfg = self._config
        if cfg.ig_session_path.exists():
            self._client.load_settings(cfg.ig_session_path)
        self._client.login(cfg.ig_username, cfg.ig_password)
        self._client.dump_settings(cfg.ig_session_path)

    def collection_medias(self, name: str) -> list[ReelMeta]:
        collections = self._client.collections()
        match = next((c for c in collections if c.name == name), None)
        if match is None:
            return []
        medias = self._client.collection_medias(match.id)
        return [
            ReelMeta(
                pk=str(m.pk), shortcode=m.code,
                url=f"https://www.instagram.com/reel/{m.code}/",
                author=m.user.username, caption=m.caption_text or "",
                taken_at=m.taken_at.date().isoformat(), collection=name,
            )
            for m in medias
        ]


def _ytdlp_download(url: str, dest_dir: Path, shortcode: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{shortcode}.mp4"
    subprocess.run(
        ["yt-dlp", "-o", str(out), "-f", "mp4", url], check=True,
        capture_output=True, text=True,
    )
    return out


def download_reel(
    url: str, dest_dir: Path, shortcode: str, *, downloader=_ytdlp_download
) -> Path:
    return downloader(url, dest_dir, shortcode)


def collect(conn, config: Config, source, *, backlog: bool = False,
            downloader=_ytdlp_download) -> int:
    """Fetch configured collections, download+enqueue unseen reels.

    backlog only changes intent/logging; the seen-set already makes both
    incremental and full passes idempotent.
    """
    seen = db.seen_pks(conn)
    enqueued = 0
    for name in config.collections:
        for reel in source.collection_medias(name):
            if reel.pk in seen:
                continue
            download_reel(reel.url, config.queue_dir, reel.shortcode,
                          downloader=downloader)
            if db.enqueue(conn, reel):
                enqueued += 1
                seen.add(reel.pk)
    return enqueued
