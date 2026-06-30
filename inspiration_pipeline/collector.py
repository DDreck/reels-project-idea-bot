"""Poll Instagram collections, download new reels, enqueue them."""
import subprocess
import sys
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
        """Authenticate with Instagram, loading and saving the session file."""
        cfg = self._config
        if cfg.ig_session_path.exists():
            self._client.load_settings(cfg.ig_session_path)
        self._client.login(cfg.ig_username, cfg.ig_password)
        self._client.dump_settings(cfg.ig_session_path)

    def collection_medias(self, name: str) -> list[ReelMeta]:
        """Return ReelMeta for every media in the named collection.

        Args:
            name: The Instagram collection name to fetch.

        Returns:
            List of ReelMeta, or an empty list if the collection is not found.
        """
        collections = self._client.collections()
        match = next((c for c in collections if c.name == name), None)
        if match is None:
            return []
        medias = self._client.collection_medias(match.id, amount=0)
        return [
            ReelMeta(
                pk=str(m.pk), shortcode=m.code,
                url=f"https://www.instagram.com/reel/{m.code}/",
                author=m.user.username, caption=m.caption_text or "",
                taken_at=m.taken_at.date().isoformat(), collection=name,
            )
            for m in medias
        ]


def _ytdlp_download(
    url: str, dest_dir: Path, shortcode: str, cookies_path: Path | None = None
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{shortcode}.mp4"
    cmd = [sys.executable, "-m", "yt_dlp", "-o", str(out),
           "-f", "best[ext=mp4]/best"]
    if cookies_path is not None and Path(cookies_path).exists():
        cmd += ["--cookies", str(cookies_path)]
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


def download_reel(
    url: str, dest_dir: Path, shortcode: str, *, cookies_path: Path | None = None,
    downloader=_ytdlp_download,
) -> Path:
    """Download a reel video to dest_dir using yt-dlp.

    Args:
        url: Direct URL of the reel.
        dest_dir: Directory to write the downloaded file.
        shortcode: Reel shortcode used as the output filename stem.
        cookies_path: Optional Netscape cookies file for Instagram auth.
        downloader: Callable matching ``_ytdlp_download`` signature (test seam).

    Returns:
        Path to the downloaded mp4 file.
    """
    return downloader(url, dest_dir, shortcode, cookies_path=cookies_path)


def collect(conn, config: Config, source, *, backlog: bool = False,
            downloader=_ytdlp_download) -> int:
    """Fetch configured collections, download+enqueue unseen reels.

    backlog only changes intent/logging; the seen-set already makes both
    incremental and full passes idempotent.
    """
    seen = db.seen_pks(conn)
    cookies_path = config.ig_session_path.parent / "ig_cookies.txt"
    enqueued = 0
    for name in config.collections:
        for reel in source.collection_medias(name):
            if reel.pk in seen:
                continue
            download_reel(reel.url, config.queue_dir, reel.shortcode,
                          cookies_path=cookies_path, downloader=downloader)
            if db.enqueue(conn, reel):
                enqueued += 1
                seen.add(reel.pk)
    return enqueued
