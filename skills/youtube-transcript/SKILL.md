---
name: youtube-transcript
description: Get the transcript of a YouTube video from its link, using existing captions (fast, no download) with a local Whisper fallback. Use when asked to transcribe, summarize, quote or take notes on a YouTube video.
---

# YouTube transcript

The tool is `scripts/yt-transcript.py` in this repo (copy it next to this skill if you
install the skill elsewhere). It reads the captions YouTube already serves, so it is
near-instant and downloads no video or audio.

## Steps

1. Run it on the link. `uv run` installs the one dependency on the fly:
   ```bash
   uv run scripts/yt-transcript.py "<url>" -f md -o /tmp/transcript.md
   ```
   No `uv`? `pip install youtube-transcript-api` then `python3 scripts/yt-transcript.py ...`.
2. Pick the format for the job:
   - `-f text` (default): clean paragraphs, best for summarizing or feeding to a model.
   - `-f md`: title, plus a clickable timestamp on every paragraph, best for notes and quotes.
   - `-f srt` / `-f json`: per-caption timing.
3. Languages: `-l ko en` sets the preference order (default `en ko`). Manual captions
   win over auto-generated ones. `--list` shows which tracks exist.
4. If it says the video has no captions, re-run with Whisper (slower, runs locally,
   needs ffmpeg):
   ```bash
   uv run --with yt-dlp --with faster-whisper scripts/yt-transcript.py "<url>" --whisper
   ```
5. Read the output file rather than pasting a long transcript into chat. When summarizing,
   cite timestamps from the `md` format.

## Errors

- `IpBlocked` / `RequestBlocked`: YouTube blocks many cloud and datacenter IPs. Run it on
  a home or office connection (the user's own computer) instead.
- `AgeRestricted` / `VideoUnavailable`: the video can't be read without signing in.
