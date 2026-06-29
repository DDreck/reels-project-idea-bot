"""Configuration loading for the inspiration pipeline."""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    collections: list[str]
    output_dir: Path
    queue_dir: Path
    db_path: Path
    whisper_model: str
    batch_size: int
    keep_originals: bool
    max_attempts: int
    dreck_host: str
    dreck_user: str
    dreck_mac: str
    dreck_scratch_dir: str
    dreck_sleep_cmd: str
    claude_bin: str
    ig_username: str
    ig_password: str
    ig_session_path: Path


def _require(env: dict[str, str | None], key: str) -> str:
    value = env.get(key)
    if not value:
        raise ConfigError(f"Missing required secret {key} in .env")
    return value


def load_config(config_path: Path, env_path: Path | None = None) -> Config:
    """Load non-secret config from TOML and secrets from .env.

    Args:
        config_path: Path to config.toml.
        env_path: Path to .env; defaults to .env beside config_path.

    Returns:
        A populated, frozen Config.

    Raises:
        ConfigError: If a required secret is missing.
    """
    with open(config_path, "rb") as handle:
        raw = tomllib.load(handle)
    env_file = env_path or config_path.parent / ".env"
    env = {**dotenv_values(env_file), **os.environ}
    dreck = raw["dreck"]
    return Config(
        collections=list(raw["collections"]),
        output_dir=Path(raw["output_dir"]),
        queue_dir=Path(raw["queue_dir"]),
        db_path=Path(raw["db_path"]),
        whisper_model=str(raw["whisper_model"]),
        batch_size=int(raw["batch_size"]),
        keep_originals=bool(raw["keep_originals"]),
        max_attempts=int(raw["max_attempts"]),
        dreck_host=str(dreck["host"]),
        dreck_user=str(dreck["user"]),
        dreck_mac=str(dreck["mac"]),
        dreck_scratch_dir=str(dreck["scratch_dir"]),
        dreck_sleep_cmd=str(dreck["sleep_cmd"]),
        claude_bin=str(raw["claude_bin"]),
        ig_username=_require(env, "IG_USERNAME"),
        ig_password=_require(env, "IG_PASSWORD"),
        ig_session_path=Path(raw["ig_session_path"]),
    )
