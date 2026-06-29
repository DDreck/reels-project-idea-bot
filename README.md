# Inspiration Pipeline

## Overview

The Inspiration Pipeline auto-ingests saved Instagram Reels into a second-brain vault as searchable, classified atomic notes. The system runs on a Raspberry Pi as a decoupled two-stage pipeline: a collector that polls configured collections and enqueues new reels into a SQLite queue, and a processor that transcribes videos on a remote GPU (dreck's RTX 5090) and uses headless Claude Code to classify, summarize, and file notes into a Syncthing-replicated vault directory. All reasoning is done via Claude Code subscription (no per-token cost), while transcription and OCR are batched to off-hours to avoid daytime wake-ups of the GPU host.

## Architecture

```
                  ┌─────────────────── pi4 (always on) ───────────────────┐
 IG collections ─▶│  COLLECTOR (all day, ~every 4h, jittered)             │
 (bot account)    │   instagrapi → diff vs seen-set → yt-dlp download      │
 projects         │   → enqueue {url, caption, author, taken_at,           │
 looksmax         │      collection, video}                                │
 3d prints        │                         │                              │
                  │                    sqlite queue                        │
                  │                         │                              │
                  │  PROCESSOR (04:00–07:00 timer, or manual; if queue≠∅)  │
                  │   1. WoL dreck, wait for SSH                           │
                  │   2. rsync videos → dreck                              │
                  │   3. dreck(5090): faster-whisper + OCR ──┐            │
                  │   4. rsync transcripts/OCR ◀─────────────┘            │
                  │   5. sleep dreck                                       │
                  │   6. headless Claude Code: classify+summarize+file    │
                  │      → write atomic note to output dir → purge video  │
                  │      → mark filed                                      │
                  └───────────────────────────────────────────────────────┘
                       output dir = pi4's Syncthing vault copy
                       notes sync pi4 ──Syncthing──▶ pi3 (vault canonical)
```

## Important: Instagram API Terms of Service

**Use a throwaway Instagram account.** This project uses the unofficial `instagrapi` API to access saved collections. This is not an officially supported API and Instagram may take action against accounts using it. Never use your main account — use a dedicated throwaway account instead. You assume the risk of account action.

## Setup

### Prerequisites

- **pi4** (Raspberry Pi 4B+) with Python 3.12, always-on internet, Syncthing installed
- **dreck** (RTX 5090 host) accessible via SSH over LAN at a stable IP, Wake-on-LAN configured
- An **Instagram throwaway account** (created specifically for this pipeline)
- **Claude Code** subscription (for headless reasoning)

### pi4 Setup (Collector + Processor + Claude Code)

```bash
# Create venv and install dependencies
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .

# Configure the pipeline
cp config.example.toml config.toml
# Edit config.toml to set:
#   - collections: your configured Instagram collection names
#   - output_dir: path to your Syncthing vault (e.g., ~/vault/wiki/inspiration/)
#   - dreck_host, dreck_mac: dreck's SSH host and Wake-on-LAN MAC
#   - whisper_model: medium or large (larger = slower, better quality)
#   - batch_size: max reels per night (e.g., 50)
#   - keep_originals: true to archive videos to dreck instead of deleting

cp .env.example .env
# Edit .env to add:
#   - INSTAGRAM_USERNAME: your throwaway account username
#   - INSTAGRAM_PASSWORD: its password

# Ensure Claude Code CLI is installed and authenticated (subscription required)
# On pi4, run: claude login
```

### dreck Setup (One-time: Remote GPU Script + Dependencies)

```bash
# From pi4, copy the remote script to dreck's scratch directory
# Replace drew@10.0.0.76 and the destination path with your own SSH host and scratch directory.
scp remote/transcribe_ocr.py drew@10.0.0.76:C:/Users/dreww/insp_scratch/

# On dreck, install GPU dependencies (with CUDA-enabled torch and tesseract)
pip install -r remote/requirements-dreck.txt
```

## Manual Run

To update your reel vault on-demand:

```bash
inspiration process
```

This will wake dreck, transcribe all pending videos, and file them into your vault. Dreck will return to sleep when done.

## Enable Automated Schedules

To run the collector every 4 hours and the processor nightly at 04:00:

```bash
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl enable --now inspiration-collector.timer inspiration-processor.timer
```

Verify timers are active:

```bash
systemctl list-timers inspiration-collector.timer inspiration-processor.timer
```

## First Run: Processing the Backlog

If you have an existing Instagram collection you want to import retroactively:

```bash
# Enqueue the entire collection (all unseen reels)
inspiration collect --backlog

# Process them in bounded nightly batches (respects batch_size from config)
inspiration process  # runs at 04:00 nightly if schedules are enabled
```

The `--backlog` mode processes the entire collection history only once. Subsequent runs use the default mode (collect only new/changed reels). The pipeline respects `batch_size` to keep disk usage bounded — each night it processes and files a batch, then stops, resuming the next night until the backlog is empty.

## Project License

MIT. See LICENSE for details.
