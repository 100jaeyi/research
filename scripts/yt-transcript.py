#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "youtube-transcript-api>=1.2",
#   "yt-dlp",
#   "faster-whisper>=1.1",
#   "mlx-whisper; platform_system == 'Darwin' and platform_machine == 'arm64'",
# ]
# ///
"""Accurate Korean transcript of a YouTube video.

YouTube's Korean auto-captions are too inaccurate, so by default this downloads
only the audio (small, no video) and transcribes it locally with Whisper large-v3,
the most accurate open Whisper model for Korean. The fastest backend for your
machine is picked automatically:
  Apple Silicon Mac -> mlx-whisper (Metal GPU)       needs ffmpeg (brew install ffmpeg)
  NVIDIA GPU        -> faster-whisper on CUDA
  anything else     -> faster-whisper on CPU (int8)  slow with large-v3; try --fast

If the video has human-made Korean captions (rare, but exact), those are used
instead because they're instant. Auto-generated captions are never used unless
you ask for them with --source captions.

Usage:
  scripts/yt-transcript.py URL                       # plain text to stdout
  scripts/yt-transcript.py URL -f md -o notes.md     # markdown with title + timestamps
  scripts/yt-transcript.py URL --fast                # large-v3-turbo: ~3-5x faster, a bit less accurate
  scripts/yt-transcript.py URL --prompt "LLM, 에이전트, Claude"   # names/jargon to spell right
  scripts/yt-transcript.py URL --source captions     # YouTube captions only (instant, lower quality)
  scripts/yt-transcript.py URL -l en                 # a non-Korean video

Formats: text (default), md, srt, json.
Run with `uv run scripts/yt-transcript.py ...` (installs everything on first run).
Running from a cloud server? YouTube blocks most datacenter IPs; set
WEBSHARE_PROXY_USERNAME/WEBSHARE_PROXY_PASSWORD or YT_PROXY_URL (captions only).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
MODELS = {  # (faster-whisper name, mlx repo)
    "accurate": ("large-v3", "mlx-community/whisper-large-v3-mlx"),
    "fast": ("large-v3-turbo", "mlx-community/whisper-large-v3-turbo"),
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


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
    """Merge segments into paragraphs of ~`every` seconds, breaking at sentence ends where possible."""
    out, buf, start = [], [], None
    for sn in snips:
        text = clean(sn["text"])
        if not text or text in {"[Music]", "[Applause]", "[음악]", "[박수]"}:
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


# ---------- captions (youtube-transcript-api) ----------

def api():
    """YouTubeTranscriptApi, routed through a proxy if one is configured.
      WEBSHARE_PROXY_USERNAME + WEBSHARE_PROXY_PASSWORD  -> Webshare rotating residential proxies
      YT_PROXY_URL=http://user:pass@host:port            -> any other HTTP(S) proxy"""
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


def fetch_captions(vid: str, lang: str, manual_only: bool):
    """Returns (segments, meta) or None if no suitable track."""
    from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

    try:
        tl = api().list(vid)
        tr = tl.find_manually_created_transcript([lang]) if manual_only else tl.find_transcript([lang])
    except (NoTranscriptFound, TranscriptsDisabled):
        return None
    snips = [{"text": s.text, "start": s.start, "duration": s.duration} for s in tr.fetch()]
    return snips, {"language": tr.language_code, "source": "auto-captions" if tr.is_generated else "captions"}


# ---------- speech-to-text (yt-dlp + Whisper) ----------

def download_audio(vid: str, d: str) -> str:
    import yt_dlp

    opts = {
        # Audio only, smallest decent stream: speech doesn't need high bitrate.
        "format": "bestaudio[abr<=80]/bestaudio/best",
        "outtmpl": os.path.join(d, "audio.%(ext)s"),
        "quiet": True, "noprogress": True, "no_warnings": True,
    }
    t = time.time()
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([f"https://www.youtube.com/watch?v={vid}"])
    path = os.path.join(d, next(f for f in os.listdir(d) if f.startswith("audio.")))
    log(f"audio downloaded ({os.path.getsize(path) / 1e6:.1f} MB, {time.time() - t:.0f}s)")
    return path


def pick_backend(want: str) -> str:
    if want != "auto":
        return want
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            if shutil.which("ffmpeg"):
                return "mlx"
            log("note: install ffmpeg (brew install ffmpeg) to use the much faster Apple GPU backend")
        except ImportError:
            pass
    return "faster-whisper"


def transcribe(path: str, lang: str, size: str, backend: str, prompt: str | None):
    fw_name, mlx_repo = MODELS[size]
    t = time.time()
    if backend == "mlx":
        import mlx_whisper

        log(f"transcribing with {mlx_repo} on Apple GPU...")
        r = mlx_whisper.transcribe(path, path_or_hf_repo=mlx_repo, language=lang, initial_prompt=prompt,
                                   condition_on_previous_text=False, word_timestamps=False)
        segs = [{"text": s["text"], "start": s["start"], "duration": s["end"] - s["start"]} for s in r["segments"]]
        model = mlx_repo.split("/")[-1]
    else:
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        try:
            import ctranslate2
            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            cuda = False
        device, ctype = ("cuda", "float16") if cuda else ("cpu", "int8")
        log(f"transcribing with faster-whisper {fw_name} on {device}"
            + ("" if cuda or size == "fast" else " (slow on CPU; --fast is ~3-5x quicker)") + "...")
        m = WhisperModel(fw_name, device=device, compute_type=ctype)
        it, _ = BatchedInferencePipeline(m).transcribe(
            path, language=lang, initial_prompt=prompt, beam_size=5, vad_filter=True,
            batch_size=16 if cuda else 8, condition_on_previous_text=False)
        segs = []
        for s in it:
            segs.append({"text": s.text, "start": s.start, "duration": s.end - s.start})
            if len(segs) % 50 == 0:
                log(f"  ...{ts(s.end)}")
        model = fw_name
    log(f"transcribed in {time.time() - t:.0f}s")
    return segs, {"language": lang, "source": f"whisper {model}"}


# ---------- output ----------

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
    ap = argparse.ArgumentParser(description="Accurate (Korean by default) transcript of a YouTube video.")
    ap.add_argument("video", help="YouTube URL or 11-character video id")
    ap.add_argument("-l", "--lang", default="ko", help="spoken language (default: ko)")
    ap.add_argument("-f", "--format", choices=["text", "md", "srt", "json"], default="text")
    ap.add_argument("-o", "--out", help="write to this file instead of stdout")
    ap.add_argument("--source", choices=["auto", "whisper", "captions"], default="auto",
                    help="auto: human-made captions if they exist, else Whisper (default). "
                         "whisper: always transcribe. captions: YouTube captions incl. auto-generated (instant, less accurate)")
    ap.add_argument("--fast", action="store_true", help="use large-v3-turbo instead of large-v3 (~3-5x faster, slightly less accurate)")
    ap.add_argument("--backend", choices=["auto", "mlx", "faster-whisper"], default="auto")
    ap.add_argument("--prompt", help="names / jargon to help spelling, e.g. 'Claude, 에이전트, MCP'")
    ap.add_argument("--para", type=float, default=30, help="seconds per paragraph in text/md (default 30)")
    ap.add_argument("--keep-audio", metavar="DIR", help="also save the downloaded audio here")
    a = ap.parse_args()

    vid = video_id(a.video)
    res = None
    if a.source in {"auto", "captions"}:
        from youtube_transcript_api import YouTubeTranscriptApiException
        try:
            res = fetch_captions(vid, a.lang, manual_only=a.source == "auto")
        except YouTubeTranscriptApiException as e:
            if a.source == "captions":
                sys.exit(f"error: {type(e).__name__}: {(str(e).strip().splitlines() or [''])[0]}")
        if res:
            log(f"using {res[1]['source']} ({res[1]['language']})")
        elif a.source == "captions":
            sys.exit(f"error: no {a.lang} captions on this video. Drop --source captions to transcribe the audio.")

    if res is None:
        with tempfile.TemporaryDirectory() as d:
            path = download_audio(vid, d)
            if a.keep_audio:
                os.makedirs(a.keep_audio, exist_ok=True)
                shutil.copy(path, os.path.join(a.keep_audio, f"{vid}{os.path.splitext(path)[1]}"))
            res = transcribe(path, a.lang, "fast" if a.fast else "accurate", pick_backend(a.backend), a.prompt)

    snips, meta = res
    title = title_of(vid) if a.format in {"md", "json"} else None
    text = render(a.format, snips, meta, vid, title, a.para)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        log(f"wrote {a.out} ({meta['source']}, {meta['language']}, {len(snips)} segments)")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
