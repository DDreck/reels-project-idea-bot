---
name: reel-clips
description: Send Drew a short video clip of a saved Instagram reel when he asks how to do an exercise, technique, or build step, or says "show me / send me the reel about X". Searches his filed inspiration reels, picks the relevant moment from the timestamped transcript, and clips it with ffmpeg.
---

# Reel Clips

Drew's saved Instagram reels are filed as notes in
`/home/drew/second-brain/wiki/inspiration/` (one `.md` per reel) with their
videos in `_videos/`. Each note has a `## Transcript` with `[m:ss]` timestamps,
`## Frames` thumbnails, and a `url:` whose `/reel/<shortcode>/` is the reel's
shortcode.

When Drew asks how to do something (an exercise, technique, build step) or to
"show / send the reel about X":

1. **Find the reel.** Search the inspiration notes for the topic — match the
   transcript, title, summary, category, or author:
   `grep -ril "<keywords>" /home/drew/second-brain/wiki/inspiration/`
   Read the best match. Take the shortcode from its `url:` frontmatter.

2. **Pick the moment.** From the note's timestamped `## Transcript`, choose the
   start and end `[m:ss]` of the part that answers Drew (where the move is
   shown/explained). Keep it tight (a few seconds up to ~20s). If the whole
   reel is the demo, clip the whole thing.

3. **Make the clip:**
   `cd /home/drew/inspiration-pipeline && .venv/bin/python tools/clip.py <shortcode> <start> <end>`
   It prints the path to the clip mp4.

4. **Send that mp4 to Drew over Telegram** (attach it), with one line on what it
   shows and the source author.

## Notes
- Times accept `m:ss` or seconds — read them from the transcript markers.
- If a match has no saved video, send the reel `url:` instead.
- Prefer the single most relevant reel; offer others only if asked.
