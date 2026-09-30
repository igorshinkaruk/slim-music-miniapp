"""Track ingestion: direct audio URLs and YouTube via yt-dlp."""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config

logger = logging.getLogger("slim.media")

AUDIO_EXTS = {".mp3", ".m4a", ".ogg", ".oga", ".opus", ".wav", ".flac", ".aac", ".webm"}
YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{6,})",
    re.I,
)


def is_youtube_url(url: str) -> bool:
    return bool(YT_RE.search(url)) or "youtube.com" in urlparse(url).netloc.lower() or "youtu.be" in urlparse(url).netloc.lower()


def _guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in AUDIO_EXTS:
        if path.endswith(ext):
            return ext
    return ".mp3"


def probe_duration(path: Path) -> int:
    """Return duration in seconds via ffprobe, or 0 on failure."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            timeout=30,
            stderr=subprocess.DEVNULL,
        )
        return max(0, int(float(out.decode().strip())))
    except Exception:
        logger.debug("ffprobe failed for %s", path, exc_info=True)
        return 0


async def download_direct_audio(url: str) -> dict[str, Any]:
    """Download direct audio URL into MEDIA_DIR. Returns metadata dict."""
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ext = _guess_ext_from_url(url)
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = config.MEDIA_DIR / fname

    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "").lower()
            if "html" in ctype and not any(x in ctype for x in ("audio", "octet", "mpeg", "ogg", "wav")):
                # still allow if URL looks like audio
                if ext not in AUDIO_EXTS:
                    raise ValueError("URL не виглядає як аудіофайл")
            total = 0
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    total += len(chunk)
                    if total > config.MAX_AUDIO_BYTES:
                        f.close()
                        dest.unlink(missing_ok=True)
                        raise ValueError(f"Файл завеликий (ліміт {config.MAX_AUDIO_BYTES // (1024*1024)} МБ)")
                    f.write(chunk)

    duration = await asyncio.to_thread(probe_duration, dest)
    title = Path(urlparse(url).path).stem or "Аудіо"
    title = title.replace("_", " ").replace("%20", " ")[:200] or "Аудіо"

    return {
        "title": title,
        "artist": "",
        "source_type": "mp3" if ext == ".mp3" else "audio",
        "source_url": url,
        "stream_url": f"/media/{fname}",
        "local_path": str(dest),
        "thumbnail_url": None,
        "duration_sec": duration,
    }


def _yt_extract_sync(url: str) -> dict[str, Any]:
    """Run yt-dlp to download best audio and extract metadata."""
    if not config.YOUTUBE_ENABLED:
        raise ValueError("YouTube вимкнено (YOUTUBE_ENABLED=0)")

    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(config.MEDIA_DIR / f"{uuid.uuid4().hex}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "5",
        "--max-filesize",
        str(config.MAX_AUDIO_BYTES),
        "--write-info-json",
        "-o",
        out_tmpl,
        "--no-warnings",
        "--newline",
        url,
    ]
    # Prefer mp3 via ffmpeg if available; fall back without -x if ffmpeg missing
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:
        raise ValueError("yt-dlp не встановлено. pip install yt-dlp") from e

    if proc.returncode != 0:
        # retry without extract/convert (keep original audio)
        out_tmpl2 = str(config.MEDIA_DIR / f"{uuid.uuid4().hex}.%(ext)s")
        cmd2 = [
            "yt-dlp",
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--max-filesize",
            str(config.MAX_AUDIO_BYTES),
            "-o",
            out_tmpl2,
            "--no-warnings",
            "--print",
            "%(title)s\t%(uploader)s\t%(duration)s\t%(thumbnail)s\t%(filepath)s",
            url,
        ]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
        if proc2.returncode != 0:
            err = (proc.stderr or proc2.stderr or "")[-500:]
            raise ValueError(f"yt-dlp помилка: {err or 'unknown'}")
        line = (proc2.stdout or "").strip().splitlines()[-1] if proc2.stdout else ""
        parts = line.split("\t")
        title = parts[0] if parts else "YouTube"
        artist = parts[1] if len(parts) > 1 else ""
        try:
            duration = int(float(parts[2])) if len(parts) > 2 and parts[2] not in ("NA", "", "None") else 0
        except ValueError:
            duration = 0
        thumb = parts[3] if len(parts) > 3 and parts[3] not in ("NA", "None") else None
        filepath = parts[4] if len(parts) > 4 else ""
        if not filepath or not Path(filepath).exists():
            # find newest file in media dir matching uuid prefix from out_tmpl2
            raise ValueError("Не вдалося завантажити аудіо з YouTube")
        fname = Path(filepath).name
        return {
            "title": (title or "YouTube")[:300],
            "artist": (artist or "")[:300],
            "source_type": "youtube",
            "source_url": url,
            "stream_url": f"/media/{fname}",
            "local_path": filepath,
            "thumbnail_url": thumb,
            "duration_sec": duration,
        }

    # success with -x: find the mp3 and optional info json
    # yt-dlp writes to out_tmpl with extension
    media_files = sorted(config.MEDIA_DIR.glob(Path(out_tmpl).name.replace("%(ext)s", "*")), key=lambda p: p.stat().st_mtime, reverse=True)
    # Better: parse from stdout or find by uuid prefix
    prefix = Path(out_tmpl).name.split(".%")[0]
    candidates = [p for p in config.MEDIA_DIR.iterdir() if p.name.startswith(prefix) and not p.name.endswith(".json")]
    if not candidates:
        raise ValueError("Файл після yt-dlp не знайдено")
    dest = candidates[0]
    info_path = config.MEDIA_DIR / f"{prefix}.info.json"
    title, artist, duration, thumb = "YouTube", "", 0, None
    if info_path.exists():
        import json

        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            title = info.get("title") or title
            artist = info.get("uploader") or info.get("channel") or ""
            duration = int(info.get("duration") or 0)
            thumb = info.get("thumbnail")
        except Exception:
            pass
        info_path.unlink(missing_ok=True)
    if not duration:
        duration = probe_duration(dest)

    return {
        "title": (title or "YouTube")[:300],
        "artist": (artist or "")[:300],
        "source_type": "youtube",
        "source_url": url,
        "stream_url": f"/media/{dest.name}",
        "local_path": str(dest),
        "thumbnail_url": thumb,
        "duration_sec": duration,
    }


async def ingest_url(url: str) -> dict[str, Any]:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Потрібен http(s) URL")
    if is_youtube_url(url):
        return await asyncio.to_thread(_yt_extract_sync, url)
    # direct audio
    path_l = urlparse(url).path.lower()
    if any(path_l.endswith(ext) for ext in AUDIO_EXTS) or "audio" in url.lower():
        return await download_direct_audio(url)
    # try direct anyway if content-type looks audio — download_direct will check
    return await download_direct_audio(url)
