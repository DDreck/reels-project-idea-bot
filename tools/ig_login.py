"""One-time Instagram login to establish a trusted session for the collector.

Two modes:

1. Session-cookie reuse (recommended, bypasses the login checkpoint):
   Log into instagram.com in any browser as the bot account, copy the
   ``sessionid`` cookie (DevTools -> Application -> Cookies -> instagram.com),
   then run:
       python tools/ig_login.py --sessionid
   and paste it at the secure prompt. Instagram already trusts a session
   created by a real browser, so no "legacy challenge" is raised.

2. Username/password (may hit a checkpoint):
       python tools/ig_login.py
   Prompts for an email/SMS code if Instagram asks. Persists a stable device
   first so retries reuse the same client identity.

Either way a trusted ``session.json`` is saved and the collector reuses it
non-interactively.
"""
import argparse
import getpass
from pathlib import Path

from inspiration_pipeline.config import load_config


def _code_handler(username: str, choice: object) -> str:
    """Prompt for the verification code Instagram sent (email/SMS)."""
    return input(f"Verification code for {username} (method={choice}): ").strip()


def _login_password(client, cfg) -> int:
    from instagrapi.exceptions import ChallengeRequired

    client.challenge_code_handler = _code_handler
    try:
        client.login(cfg.ig_username, cfg.ig_password)
    except ChallengeRequired:
        info = (client.last_json or {}).get("challenge", {})
        ref = info.get("url") or info.get("api_path") or "(none)"
        print("\nInstagram requires a checkpoint cleared via a real client.")
        print("Recommended: re-run with --sessionid using a browser cookie.")
        print("Challenge reference:", ref)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Establish an Instagram session.")
    parser.add_argument(
        "--sessionid", action="store_true",
        help="Authenticate with a sessionid cookie from a browser login.",
    )
    args = parser.parse_args()

    cfg = load_config(Path("config.toml"))
    from instagrapi import Client

    client = Client()
    if cfg.ig_session_path.exists():
        client.load_settings(cfg.ig_session_path)
    else:
        client.dump_settings(cfg.ig_session_path)  # stable device for retries

    if args.sessionid:
        sid = getpass.getpass("Paste Instagram sessionid cookie: ").strip()
        client.login_by_sessionid(sid)
    elif _login_password(client, cfg) != 0:
        return 1

    client.dump_settings(cfg.ig_session_path)
    print(f"Login OK; trusted session saved to {cfg.ig_session_path}")
    print("Verifying:", client.account_info().username)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
