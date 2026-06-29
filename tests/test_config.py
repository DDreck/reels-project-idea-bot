import pytest

from inspiration_pipeline.config import ConfigError, load_config


def test_load_config_reads_toml_and_env(config_files):
    cfg_path, env_path = config_files
    cfg = load_config(cfg_path, env_path)
    assert cfg.collections == ["projects", "looksmax"]
    assert cfg.batch_size == 50
    assert cfg.keep_originals is False
    assert cfg.dreck_mac == "AA-BB-CC-DD-EE-FF"
    assert cfg.ig_username == "bot"
    assert cfg.ig_password == "pw"


def test_load_config_missing_secret_raises(config_files):
    cfg_path, env_path = config_files
    env_path.write_text("IG_USERNAME=bot\n", encoding="utf-8")  # no password
    with pytest.raises(ConfigError, match="IG_PASSWORD"):
        load_config(cfg_path, env_path)
