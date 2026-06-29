import json
from pathlib import Path

from inspiration_pipeline import db, processor
from inspiration_pipeline.models import Classification, ReelMeta


def _reel(pk):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url="u", author="@a", caption="c",
                    taken_at="2026-06-25", collection="projects")


class FakeDreck:
    def __init__(self, scratch: Path, reachable=True):
        self.scratch = scratch
        self.reachable = reachable
        self.calls: list[str] = []

    def wake(self, config):  # noqa: D401
        self.calls.append("wake")

    def wait_for_ssh(self, config):
        self.calls.append("wait_for_ssh")
        return self.reachable

    def push(self, config, files):
        self.calls.append("push")

    def run_transcription(self, config):
        self.calls.append("run_transcription")

    def pull_results(self, config, local_dir):
        self.calls.append("pull_results")
        # simulate dreck returning <stem>.json for each queued video
        for video in Path(config.queue_dir).glob("*.mp4"):
            (local_dir / f"{video.stem}.json").write_text(
                json.dumps({"transcript": "T", "ocr": "O"}), encoding="utf-8"
            )

    def sleep_host(self, config):
        self.calls.append("sleep_host")


def _seed(config):
    config.queue_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(config.db_path)
    for pk in ("1", "2"):
        db.enqueue(conn, _reel(pk))
        (config.queue_dir / f"sc{pk}.mp4").write_bytes(b"x")
    return conn


def test_process_files_all_reels(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "queue_dir", tmp_path / "q")
    object.__setattr__(config, "output_dir", tmp_path / "out")
    conn = _seed(config)
    cls = Classification("c", "T", "s", [], "Projects")
    n = processor.process(conn, config, dreck_mod=FakeDreck(config.queue_dir),
                          classifier=lambda *a, **k: cls)
    assert n == 2
    assert len(db.records_by_status(conn, "filed")) == 2


def test_process_empty_queue_noop(tmp_path, dummy_config):
    object.__setattr__(dummy_config, "queue_dir", tmp_path / "q")
    conn = db.connect(dummy_config.db_path)
    fake = FakeDreck(tmp_path)
    assert processor.process(conn, dummy_config, dreck_mod=fake) == 0
    assert fake.calls == []


def test_process_dreck_unreachable_leaves_queued(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "queue_dir", tmp_path / "q")
    conn = _seed(config)
    n = processor.process(conn, config,
                          dreck_mod=FakeDreck(config.queue_dir, reachable=False))
    assert n == 0
    assert len(db.records_by_status(conn, "downloaded")) == 2
