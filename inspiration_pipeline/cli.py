"""Command-line entrypoints: collect and process."""
import argparse
from pathlib import Path

from inspiration_pipeline import collector, db, processor
from inspiration_pipeline.config import Config, load_config


def _run_collect(config: Config, backlog: bool) -> int:
    conn = db.connect(config.db_path)
    source = collector.InstagramSource(config)
    source.login()
    return collector.collect(conn, config, source, backlog=backlog)


def _run_process(config: Config) -> int:
    conn = db.connect(config.db_path)
    return processor.process(conn, config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inspiration")
    sub = parser.add_subparsers(dest="command", required=True)
    collect_p = sub.add_parser("collect", help="Poll collections and enqueue reels")
    collect_p.add_argument("--backlog", action="store_true")
    collect_p.add_argument("--config", default="config.toml", type=Path)
    process_p = sub.add_parser("process", help="Transcribe and file queued reels")
    process_p.add_argument("--config", default="config.toml", type=Path)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "collect":
        count = _run_collect(config, args.backlog)
        print(f"Enqueued {count} reel(s)")
    else:
        count = _run_process(config)
        print(f"Filed {count} reel(s)")
    return 0
