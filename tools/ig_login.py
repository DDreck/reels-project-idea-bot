"""One-time interactive Instagram login to clear a challenge and save a session.

Run this on the collector host when ``inspiration collect`` reports
``ChallengeRequired``. It persists a STABLE device fingerprint (so retries don't
each look like a new device), prompts for the email/SMS code if Instagram asks,
and saves a trusted session so the collector can then run non-interactively.

If Instagram returns a "legacy challenge flow", the checkpoint must be cleared
once from a real Instagram client (app or instagram.com) before this will
succeed -- see the printed guidance.

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
    from instagrapi.exceptions import ChallengeRequired

    client = Client()
    if cfg.ig_session_path.exists():
        client.load_settings(cfg.ig_session_path)
    else:
        # Persist the generated device NOW so every retry reuses the same
        # client settings / device identifiers (what Instagram asks for).
        client.dump_settings(cfg.ig_session_path)
    client.challenge_code_handler = _code_handler
    try:
        client.login(cfg.ig_username, cfg.ig_password)
    except ChallengeRequired:
        info = (client.last_json or {}).get("challenge", {})
        url = info.get("url") or info.get("api_path") or "(none provided)"
        print("\nInstagram requires a checkpoint to be cleared manually first.")
        print("1. Open instagram.com or the app, logged in as", cfg.ig_username)
        print("2. Approve the recent login / clear any security checkpoint.")
        print("   Challenge reference:", url)
        print("3. Re-run this script (the device identity is now saved).")
        return 1
    client.dump_settings(cfg.ig_session_path)
    print(f"Login OK; trusted session saved to {cfg.ig_session_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
