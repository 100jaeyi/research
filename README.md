# Research

Jaeyi's personal research feed: a daily digest of trending open source on GitHub,
with a focus on **agent skills, MCP servers and agent frameworks**.

## Layout

| Path | What it is |
| --- | --- |
| `digests/YYYY-MM-DD.md` | One digest per day, newest wins. Start here. |
| `CRITERIA.md` | What counts as interesting, and what gets filtered out. |
| `scripts/crawl.sh` | The GitHub searches each run starts from (raw candidates as TSV). |
| `scripts/yt-transcript.py` | Transcript of a YouTube video from its link. See below. |
| `skills/youtube-transcript/` | Agent skill wrapping that script, for Claude sessions. |

## How a digest is made

1. Run `scripts/crawl.sh` to pull candidates from the GitHub search API
   (new repos by stars, agent skills, MCP servers, agent frameworks).
2. Filter with `CRITERIA.md`: drop spam rings, piracy, malware and dupes.
3. Compare with the previous digest so repeats are marked, not re-listed.
4. Write `digests/YYYY-MM-DD.md` using the format below.

A scheduled run does this every day at 8 AM Asia/Seoul.

## Digest format

```
# Research digest: YYYY-MM-DD
> One-line TL;DR of the day.

## Top picks        (3-5 things worth opening today, with why)
## Trending repos   (table: repo, stars, age, language, one-line why)
## Agent skills     (new SKILL.md skills and skill collections)
## MCP servers      (new or rising MCP servers)
## Agent frameworks & tooling
## Watch out        (spam, star farming, risky repos seen this run)
## Sources          (queries and pages used)
```

Star counts are a snapshot at crawl time. "Age" is days since the repo was created.

## YouTube transcripts

Accurate Korean transcripts. YouTube's Korean auto-captions are too rough, so the script downloads
only the audio and transcribes it locally with **Whisper large-v3**, using the fastest backend for
your machine (Apple GPU via mlx-whisper, NVIDIA via faster-whisper, otherwise CPU).
If a video has human-made Korean captions, it uses those instead because they are exact and instant.

```bash
brew install uv ffmpeg                                         # once (ffmpeg enables the Apple GPU path)
uv run scripts/yt-transcript.py "https://youtu.be/VIDEO_ID"                 # plain text
uv run scripts/yt-transcript.py "<url>" -f md -o notes.md                   # markdown + timestamps
uv run scripts/yt-transcript.py "<url>" --fast                              # large-v3-turbo, ~3-5x faster
uv run scripts/yt-transcript.py "<url>" --prompt "Claude, 에이전트, MCP"     # spell names/jargon right
uv run scripts/yt-transcript.py "<url>" --source captions                   # YouTube captions only
uv run scripts/yt-transcript.py "<url>" -l en                               # non-Korean video
```

The first run downloads the model (~3 GB for large-v3, ~1.6 GB for turbo). Run it on your own
computer: YouTube blocks most cloud IPs, including the one Claude's cloud sessions use.
