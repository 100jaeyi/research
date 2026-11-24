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

```bash
uv run scripts/yt-transcript.py "https://youtu.be/VIDEO_ID"              # plain text
uv run scripts/yt-transcript.py "<url>" -f md -o notes.md                # markdown + timestamps
uv run scripts/yt-transcript.py "<url>" -l ko en                         # language preference
uv run --with yt-dlp --with faster-whisper scripts/yt-transcript.py "<url>" --whisper   # no captions
```

It uses the captions YouTube already has (manual, then auto-generated), so it takes about a
second and downloads nothing. Whisper is only used with `--whisper`, for videos without captions.
No `uv`? `pip install youtube-transcript-api` and use `python3`. Run it from your own computer:
YouTube blocks most cloud IPs, including the one Claude's cloud sessions use.
