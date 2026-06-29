from pathlib import Path

import pytest

from inspiration_pipeline.config import Config


@pytest.fixture
def config_files(tmp_path: Path) -> tuple[Path, Path]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'collections = ["projects", "looksmax"]\n'
        f'output_dir = "{(tmp_path / "out").as_posix()}"\n'
        f'queue_dir = "{(tmp_path / "queue").as_posix()}"\n'
        f'db_path = "{(tmp_path / "insp.db").as_posix()}"\n'
        f'ig_session_path = "{(tmp_path / "session.json").as_posix()}"\n'
        'whisper_model = "large-v3"\n'
        "batch_size = 50\n"
        "keep_originals = false\n"
        "max_attempts = 3\n"
        'claude_bin = "claude"\n'
        "[dreck]\n"
        'host = "dreck.local"\n'
        'user = "youruser"\n'
        'mac = "AA-BB-CC-DD-EE-FF"\n'
        'scratch_dir = "C:/scratch"\n'
        'sleep_cmd = "sleepnow"\n',
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("IG_USERNAME=bot\nIG_PASSWORD=pw\n", encoding="utf-8")
    return cfg, env


@pytest.fixture
def dummy_config(tmp_path) -> Config:
    return Config(
        collections=["projects"], output_dir=tmp_path / "out",
        queue_dir=tmp_path / "q", db_path=tmp_path / "db.db",
        whisper_model="large-v3", batch_size=50,
        keep_originals=False, max_attempts=3, dreck_host="h", dreck_user="u",
        dreck_mac="m", dreck_scratch_dir="C:/s", dreck_sleep_cmd="s",
        claude_bin="claude", ig_username="bot", ig_password="pw",
        ig_session_path=tmp_path / "session.json",
    )
