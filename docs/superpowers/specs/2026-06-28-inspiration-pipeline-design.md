# Inspiration Pipeline — Design

**Date:** 2026-06-28
**Owner:** drew (jawiend@sandia.gov)
**Status:** Approved design, ready for implementation plan

## Problem

Drew saves engineering builds, 3D prints, and "looksmax" content (posture, workouts,
physique) as Instagram Reels across multiple saved collections. They rot in a
forgotten saves folder. The goal: auto-ingest saved reels into the second-brain vault
as searchable, classified, atomic notes — with zero change to how Drew saves reels.

This is also a **public GitHub project** (MIT), so the code must be reusable by others
and must never leak secrets or personal vault data.

## Goals

- Keep saving reels to Instagram collections exactly as today (no behavior change).
- New reels appear automatically as atomic markdown notes in the vault, classified and
  summarized, with the source link and dates.
- Use the **Claude Code subscription** for all reasoning work (classify/summarize/file)
  to avoid per-token API cost; use the **5090 (dreck)** only for what the subscription
  can't do (Whisper transcription + OCR), batched to off-hours.
- The always-on collector runs on a Raspberry Pi.
- Bounded disk usage regardless of backlog size.
- Public-repo-safe: no secrets, no vault content committed; reusable via config.

## Non-goals

- Migrating the second brain vault from pi3's SD card to its new 1 TB M.2 SSD. This is
  separate vault infrastructure work and is transparent to this pipeline (pi4 writes
  notes via Syncthing regardless of pi3's storage backend).
- A web UI or hosted service. This is a personal automation with a CLI/agent interface.
- Telegram notifications (deferred; not in v1).

## Chosen decisions

| Decision | Choice |
|---|---|
| Ingestion | instagrapi scrapes saved collections via a throwaway bot account (zero behavior change) |
| Collections | Poll all configured collections (`projects`, `looksmax`, `3d prints`); list is config |
| Categories | Claude-managed registry, not a hardcoded enum; grows organically |
| Output | Per-reel atomic markdown notes in a configurable output directory |
| Transcription/OCR | faster-whisper + OCR on dreck's RTX 5090, off-hours (04:00–07:00) |
| Reasoning/filing | Headless Claude Code (`claude -p`), subscription auth, on pi4 |
| Collector host | pi4 (10.0.0.10), Syncthing peer of the vault |
| Processor host (Claude) | pi4 |
| Processor host (GPU) | dreck (10.0.0.76, WoL `60-CF-84-84-1B-D9`) |
| Video retention | Delete after filing; optional flag to archive originals to dreck |
| Manual run | Wakes dreck and transcribes immediately (daytime WoL acceptable) |
| Backlog import | One-shot mode, processed in bounded batches |

## Architecture

Two decoupled stages joined by a sqlite queue on pi4.

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

Rationale for the split: collecting is cheap and must be always-on with a human-like
residential IP; transcription needs the GPU and Claude reasoning is best batched. The
sqlite queue makes the pipeline crash-safe — a failed night simply retries the next.

## Components

### 1. Collector (pi4, all day)

- instagrapi logged in as a **throwaway bot account**, session persisted to disk to
  avoid repeated logins (the main ban trigger). Login from pi4's residential IP.
- systemd timer, **~every 4h with jitter** (human-like), no-op if nothing new.
- Iterates the **configured collection list**; for each, diffs media PKs against the
  sqlite `seen` set.
- For each new reel: capture `url, shortcode, caption, author, taken_at, collection`;
  download video via **yt-dlp** to a queue dir; insert row with `status=downloaded`.
- On IG challenge/checkpoint: **log and stop the cycle** (no hammering); surface for
  manual re-auth. Accepts occasional babysitting as the known cost of this route.
- **Backlog mode** (`--backlog`): walk the entire collection set (not just the diff)
  and enqueue everything unseen.

Reuses the existing `rust_userbot.py` pattern (instagrapi + sqlite seen-set).

### 2. Processor (pi4 orchestration; dreck GPU; nightly or manual)

Triggered by a 04:00 systemd timer or the manual entrypoint. No-ops if queue empty.

1. **Wake dreck** via Wake-on-LAN (`60-CF-84-84-1B-D9`); poll for SSH readiness.
   Reuses rust_raid WoL/SSH lore.
2. **rsync** queued videos to a scratch dir on dreck.
3. On dreck's 5090: **faster-whisper** (large model) → transcript per reel;
   **OCR** = sample frames (~1 fps) → tesseract → deduped on-screen text.
4. **rsync** transcripts + OCR text back to pi4; mark `status=transcribed`.
5. **Sleep dreck** (back to standby).
6. **Headless Claude Code** (`claude -p`, subscription auth): per reel, read the
   category registry + `{caption, author, transcript, ocr, url, taken_at, collection}`,
   classify (assigning an existing category or proposing a new one), summarize, write
   the atomic note to the output dir, **purge the video**, mark `status=filed`.

**Manual run:** same processor, invoked on demand (when Drew tells Claude Code "update
my reel vault"). Wakes dreck and transcribes immediately rather than deferring to 04:00.

### 3. Categories (Claude-managed registry)

- `<output_dir>/_categories.md` lists known categories with one-line descriptions
  (e.g. `workout`, `posture`, `physique`, `3d-print`, `engineering-build`).
- On each run Claude reads the registry, assigns each reel to an existing category, and
  **may append a new category** when none fits. The collection of origin is a strong
  prior but not the final answer (collections are mixed, e.g. looksmax holds posture
  *and* workouts).
- Taxonomy grows organically; no code change to add a category.

### 4. Output (per-reel atomic notes)

Notes written to a **configurable output directory**. On Drew's setup this points at
pi4's Syncthing copy of the vault: `wiki/inspiration/`. Section contents:
`_index.md` (dashboard of recent reels + timestamps), `_categories.md` (registry), and
one atomic note per reel:

```markdown
---
type: source
source: instagram-reel
url: https://instagram.com/reel/...
author: "@builder_name"
collection: "3d prints"
category: 3d-print
captured: 2026-06-25      # when saved on IG (taken_at)
filed: 2026-06-28          # when filed into vault
status: inbox
tags: [inspiration, 3d-print]
---

# <Claude-generated title>

**Summary:** 2–3 sentences.
**Key points:** bullets (specs, steps, exercises…).

> Cross-linked to [[Projects]]  (or [[Health]] for workouts/posture)

## Transcript
<whisper text>

## On-screen text
<ocr text>
```

Workouts/posture cross-link to `[[Health]]`; builds/prints to `[[Projects]]`.
`status: inbox` lets Drew skim and promote later without Claude over-committing a reel
to a domain. Syncthing carries notes pi4 → pi3.

### 5. State & logging (sqlite on pi4)

Single `media` table drives the pipeline:

| column | purpose |
|---|---|
| `pk` / `shortcode` | IG identifiers (dedup key) |
| `url`, `author`, `caption`, `taken_at`, `collection` | reel metadata |
| `status` | `downloaded` → `transcribed` → `filed` (or `failed`) |
| `attempts`, `error` | retry tracking |
| `downloaded_at`, `transcribed_at`, `ocr_at`, `filed_at` | per-stage history |
| `created_at`, `updated_at` | row audit |

Per-stage timestamps give a queryable history of when each reel moved through each
step. The `_index.md` dashboard surfaces this in human-readable form.

## Disk management

Videos are stored on pi4 **only transiently** — needed solely for Whisper + OCR, then
**purged once a reel reaches `status=filed`**. Steady state holds only the current
queue plus what's mid-flight overnight (well under 1 GB; reels are ~5–20 MB each).

**Backlog import** is the one spike: it processes in **bounded batches** (e.g. 50
reels/night), purging each batch before fetching the next, so peak disk stays bounded
regardless of how large the backlog is.

Optional `keep_originals` flag archives videos to dreck instead of deleting. Default:
delete.

## Error handling

- Each reel carries `status` + `attempts`. One bad reel never blocks the batch.
- If dreck won't wake: skip transcription tonight, retry next batch.
- Per-reel transcription/filing failure: increment `attempts`, retry up to N, then
  `status=failed` (logged, left for manual inspection).
- IG challenge during collection: stop the cycle, log, await manual re-auth.

## Secrets & public-repo safety

- Standalone repo, **not inside the vault**. Vault is private; only code is public.
- Secrets in a gitignored `.env`; `.env.example` committed. Gitignored from day one:
  `.env`, IG **session file**, sqlite **db**, downloaded **videos**, any vault content.
- Config holds: collection list, output directory, dreck host/MAC/SSH, poll interval,
  whisper model, batch size, retention flag.
- `README.md`: architecture, setup, and an honest **instagrapi/ToS caveat** (throwaway
  account only; may break on IG changes).
- License: **MIT**.

## Testing

- **Unit:** diff/seen-set logic; sqlite state transitions; note rendering from a fixed
  reel payload; category-registry assignment/append logic.
- **Integration:** one end-to-end run on a single local sample video (skip IG) →
  transcript → filed note in a temp output dir.
- **Mock only boundaries:** Instagram API, SSH/dreck, Whisper. Do not mock the filing
  or rendering logic.

## Open follow-ups (not in this spec)

- Migrate the second brain vault on pi3 from SD card to the new 1 TB M.2 SSD. Track
  under `[[Homelab]]`. Transparent to this pipeline.
- Telegram per-batch notification (deferred).
