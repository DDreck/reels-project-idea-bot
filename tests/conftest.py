from pathlib import Path

import pytest


@pytest.fixture
def config_files(tmp_path: Path) -> tuple[Path, Path]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'collections = ["projects", "looksmax"]\n'
        f'output_dir = "{(tmp_path / "out").as_posix()}"\n'
        f'queue_dir = "{(tmp_path / "queue").as_posix()}"\n'
        f'db_path = "{(tmp_path / "insp.db").as_posix()}"\n'
        f'ig_session_path = "{(tmp_path / "session.json").as_posix()}"\n'
        "poll_interval_hours = 4.0\n"
        'whisper_model = "large-v3"\n'
        "batch_size = 50\n"
        "keep_originals = false\n"
        "max_attempts = 3\n"
        'claude_bin = "claude"\n'
        "[dreck]\n"
        'host = "10.0.0.76"\n'
        'user = "drew"\n'
        'mac = "60-CF-84-84-1B-D9"\n'
        'scratch_dir = "C:/scratch"\n'
        'sleep_cmd = "sleepnow"\n',
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("IG_USERNAME=bot\nIG_PASSWORD=pw\n", encoding="utf-8")
    return cfg, env
