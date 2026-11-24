#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["youtube-transcript-api>=1.2"]
# ///
"""Get the transcript of a YouTube video, fast.

Uses the captions YouTube already has (manual first, then auto-generated), so a
1-hour video takes about a second and nothing is downloaded. Only when a video
has no captions at all does it fall back to downloading the audio and running
Whisper locally, and only if you pass --whisper.

Usage:
  scripts/yt-transcript.py URL_OR_ID                 # plain text to stdout
  scripts/yt-transcript.py URL -f md -o notes.md     # markdown with title + timestamps
  scripts/yt-transcript.py URL -l ko en              # preferred languages, in order
  scripts/yt-transcript.py URL --list                # show available caption tracks
  scripts/yt-transcript.py URL --whisper             # allow audio+Whisper fallback

Formats: text (default), md, srt, json.
Running from a cloud server? YouTube blocks most datacenter IPs; set
WEBSHARE_PROXY_USERNAME/WEBSHARE_PROXY_PASSWORD or YT_PROXY_URL (see api()).
Run with `uv run scripts/yt-transcript.py ...` (no install needed), or
`pip install youtube-transcript-api` and use python3.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id(s: str) -> str:
    s = s.strip()
    if ID_RE.match(s):
        return s
    u = urllib.parse.urlparse(s if "://" in s else "https://" + s)
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        cand = u.path.lstrip("/").split("/")[0]
    else:
        q = urllib.parse.parse_qs(u.query)
        if "v" in q:
            cand = q["v"][0]
        else:  # /shorts/ID, /live/ID, /embed/ID, /v/ID
            parts = [p for p in u.path.split("/") if p]
            cand = parts[1] if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed", "v"} else ""
    if not ID_RE.match(cand):
        sys.exit(f"error: can't find a video id in {s!r}")
    return cand


def title_of(vid: str) -> str | None:
    """Video title via oEmbed (no API key, one small request). Best-effort."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.load(r).get("title")
    except Exception:
        return None


def ts(sec: float, srt: bool = False) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    if srt:
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def clean(t: str) -> str:
    t = t.replace("\n", " ").replace("​", "")
    return re.sub(r"\s+", " ", t).strip()


def paragraphs(snips: list[dict], every: float) -> list[tuple[float, str]]:
    """Merge caption fragments into paragraphs of ~`every` seconds,
    breaking at sentence ends where possible."""
    out, buf, start = [], [], None
    for sn in snips:
        text = clean(sn["text"])
        if not text or text in {"[Music]", "[Applause]", "[음악]"}:
            continue
        if start is None:
            start = sn["start"]
        buf.append(text)
        span = sn["start"] - start
        if (span >= every and re.search(r"[.!?。？！]$", text)) or span >= every * 2:
            out.append((start, " ".join(buf)))
            buf, start = [], None
    if buf:
        out.append((start or 0.0, " ".join(buf)))
    return out


def api():
    """YouTubeTranscriptApi, routed through a proxy if one is configured.
    YouTube blocks most cloud/datacenter IPs; on a home connection no proxy is needed.
      WEBSHARE_PROXY_USERNAME + WEBSHARE_PROXY_PASSWORD  -> Webshare rotating residential proxies
      YT_PROXY_URL=http://user:pass@host:port            -> any other HTTP(S) proxy"""
    import os
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

    if os.environ.get("WEBSHARE_PROXY_USERNAME"):
        cfg = WebshareProxyConfig(proxy_username=os.environ["WEBSHARE_PROXY_USERNAME"],
                                  proxy_password=os.environ.get("WEBSHARE_PROXY_PASSWORD", ""))
    elif os.environ.get("YT_PROXY_URL"):
        cfg = GenericProxyConfig(http_url=os.environ["YT_PROXY_URL"], https_url=os.environ["YT_PROXY_URL"])
    else:
        cfg = None
    return YouTubeTranscriptApi(proxy_config=cfg)


def fetch_captions(vid: str, langs: list[str]):
    from youtube_transcript_api import NoTranscriptFound

    tl = api().list(vid)
    try:
        tr = tl.find_transcript(langs)  # manual before auto-generated
    except NoTranscriptFound:
        tr = next(iter(tl))  # nothing in the preferred languages: take what exists
        codes = {t.language_code for t in tr.translation_languages}
        if langs and tr.is_translatable and langs[0] in codes:
            tr = tr.translate(langs[0])  # YouTube machine-translates the track
    f = tr.fetch()
    snips = [{"text": s.text, "start": s.start, "duration": s.duration} for s in f]
    meta = {"language": tr.language_code, "source": "auto-captions" if tr.is_generated else "captions"}
    return snips, meta


def whisper(vid: str, model: str):
    try:
        import yt_dlp  # noqa: F401
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("error: --whisper needs yt-dlp and faster-whisper (and ffmpeg). Try:\n"
                 "  uv run --with yt-dlp --with faster-whisper scripts/yt-transcript.py URL --whisper")
    import tempfile, os, yt_dlp

    with tempfile.TemporaryDirectory() as d:
        opts = {"format": "bestaudio/best", "outtmpl": os.path.join(d, "a.%(ext)s"), "quiet": True, "noprogress": True}
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([f"https://www.youtube.com/watch?v={vid}"])
        path = os.path.join(d, os.listdir(d)[0])
        print(f"transcribing with Whisper ({model})...", file=sys.stderr)
        segs, info = WhisperModel(model, compute_type="int8").transcribe(path, vad_filter=True)
        snips = [{"text": s.text, "start": s.start, "duration": s.end - s.start} for s in segs]
    return snips, {"language": info.language, "source": f"whisper-{model}"}


def render(fmt: str, snips, meta, vid, title, every) -> str:
    url = f"https://www.youtube.com/watch?v={vid}"
    if fmt == "json":
        return json.dumps({"video_id": vid, "url": url, "title": title, **meta, "segments": snips}, ensure_ascii=False, indent=1)
    if fmt == "srt":
        return "\n".join(f"{i}\n{ts(s['start'], True)} --> {ts(s['start'] + s['duration'], True)}\n{clean(s['text'])}\n"
                         for i, s in enumerate(snips, 1))
    paras = paragraphs(snips, every)
    if fmt == "text":
        return "\n\n".join(p for _, p in paras) + "\n"
    head = f"# {title or vid}\n\n<{url}> · {meta['source']} · {meta['language']}\n\n"
    return head + "\n\n".join(f"[{ts(t)}]({url}&t={int(t)}s) {p}" for t, p in paras) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Get a YouTube video's transcript (captions first, Whisper fallback).")
    ap.add_argument("video", help="YouTube URL or 11-character video id")
    ap.add_argument("-l", "--lang", nargs="+", default=["en", "ko"], help="preferred caption languages, in order (default: en ko)")
    ap.add_argument("-f", "--format", choices=["text", "md", "srt", "json"], default="text")
    ap.add_argument("-o", "--out", help="write to this file instead of stdout")
    ap.add_argument("--para", type=float, default=30, help="seconds per paragraph in text/md (default 30)")
    ap.add_argument("--list", action="store_true", help="list available caption tracks and exit")
    ap.add_argument("--whisper", action="store_true", help="if there are no captions, download audio and run Whisper")
    ap.add_argument("--whisper-model", default="small", help="faster-whisper model (tiny/base/small/medium/large-v3)")
    a = ap.parse_args()

    vid = video_id(a.video)
    from youtube_transcript_api import TranscriptsDisabled, NoTranscriptFound, YouTubeTranscriptApiException

    if a.list:
        for t in api().list(vid):
            print(f"{t.language_code:8} {'auto' if t.is_generated else 'manual':6} {t.language}")
        return
    try:
        snips, meta = fetch_captions(vid, a.lang)
    except (TranscriptsDisabled, NoTranscriptFound, StopIteration):
        if not a.whisper:
            sys.exit("error: this video has no captions. Re-run with --whisper to transcribe the audio locally.")
        snips, meta = whisper(vid, a.whisper_model)
    except YouTubeTranscriptApiException as e:
        sys.exit(f"error: {type(e).__name__}: {str(e).strip().splitlines()[0] if str(e).strip() else ''}")

    title = title_of(vid) if a.format in {"md", "json"} else None
    text = render(a.format, snips, meta, vid, title, a.para)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {a.out} ({meta['source']}, {meta['language']}, {len(snips)} segments)", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
