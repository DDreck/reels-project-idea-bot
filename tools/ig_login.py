"""One-time interactive Instagram login to clear a challenge and save a session.

Run this on the collector host when ``inspiration collect`` reports
``ChallengeRequired``. It logs in, prompts for the email/SMS verification code if
Instagram asks, and persists a trusted session so the collector can then run
non-interactively (it reuses the saved ``session.json``).

Usage (from the project dir, venv active):
    python tools/ig_login.py
"""
from pathlib import Path

from inspiration_pipeline.config import load_config


def _code_handler(username: str, choice: object) -> str:
    """Prompt for the verification code Instagram sent (email/SMS)."""
    return input(f"Verification code for {username} (method={choice}): ").strip()


def main() -> int:
    cfg = load_config(Path("config.toml"))
    from instagrapi import Client

    client = Client()
    if cfg.ig_session_path.exists():
        client.load_settings(cfg.ig_session_path)
    client.challenge_code_handler = _code_handler
    client.login(cfg.ig_username, cfg.ig_password)
    client.dump_settings(cfg.ig_session_path)
    print(f"Login OK; trusted session saved to {cfg.ig_session_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
