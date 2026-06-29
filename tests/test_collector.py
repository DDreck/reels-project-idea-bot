from pathlib import Path

from inspiration_pipeline import collector, db
from inspiration_pipeline.models import ReelMeta


class FakeSource:
    def __init__(self, by_collection):
        self.by_collection = by_collection

    def collection_medias(self, name):
        return self.by_collection.get(name, [])


def _reel(pk):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url=f"u{pk}", author="@a",
                    caption="c", taken_at="2026-06-25", collection="projects")


def test_collect_enqueues_new_and_skips_seen(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "collections", ["projects"])
    object.__setattr__(config, "queue_dir", tmp_path / "q")
    conn = db.connect(config.db_path)
    db.enqueue(conn, _reel("1"))  # already seen
    source = FakeSource({"projects": [_reel("1"), _reel("2")]})
    calls = []

    def fake_dl(url, dest_dir, shortcode, **kw):
        calls.append(shortcode)
        p = Path(dest_dir) / f"{shortcode}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p

    n = collector.collect(conn, config, source, downloader=fake_dl)
    assert n == 1  # only pk 2
    assert calls == ["sc2"]
    assert db.seen_pks(conn) == {"1", "2"}
