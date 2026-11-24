---
name: youtube-transcript
description: Get an accurate transcript (Korean by default) of a YouTube video from its link by transcribing the audio locally with Whisper large-v3. Use when asked to transcribe, summarize, quote or take notes on a YouTube video.
---

# YouTube transcript

The tool is `scripts/yt-transcript.py` in this repo. YouTube's Korean auto-captions are
too inaccurate, so it downloads only the audio (yt-dlp) and transcribes it locally with
Whisper large-v3: mlx-whisper on Apple Silicon (needs ffmpeg), faster-whisper on NVIDIA GPU
or CPU. Human-made captions, when a video has them, are used instead because they're exact.

## Steps

1. Run it on the link. `uv run` installs the dependencies on the first run:
   ```bash
   uv run scripts/yt-transcript.py "<url>" -f md -o /tmp/transcript.md
   ```
   Progress goes to stderr. The first run also downloads the model (~3 GB).
2. Options:
   - `-f text` (default) clean paragraphs; `-f md` title + clickable timestamps; `-f srt` / `-f json`.
   - `--fast`: large-v3-turbo, about 3-5x faster, slightly less accurate. Use it on CPU-only machines
     or long videos when speed matters more than precision.
   - `--prompt "names, jargon"`: proper nouns and technical terms that appear in the video, so Whisper
     spells them right. Fill it from the video title/description when they have such terms.
   - `-l en` (or another code) for a non-Korean video. Default is `ko`.
   - `--source captions`: YouTube captions only, instant but rough. Only when the user asks for speed.
3. Read the output file rather than pasting a long transcript into chat. When summarizing,
   cite timestamps from the `md` format.

## Errors

- Sign-in / bot check or HTTP 403 from yt-dlp: YouTube blocks most cloud and datacenter IPs.
  Run it on the user's own computer. Updating yt-dlp (`uv run --upgrade ...`) fixes most other
  download errors.
- Age-restricted or private videos can't be fetched without the user's cookies.
