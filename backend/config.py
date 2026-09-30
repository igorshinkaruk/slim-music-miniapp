"""Application configuration from environment."""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("slim.config")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BRAND_NAME = os.getenv("BRAND_NAME", "Slim Music")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip() or os.getenv("MUSIC_BOT_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "8764474734").split(",")
    if x.strip().isdigit()
}
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://127.0.0.1:8001/")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("RENDER_DATABASE_URL") or "").strip()
_default_db = "/tmp/slim_music.db" if os.getenv("RENDER") else str(ROOT / "data" / "slim_music.db")
DB_PATH = os.getenv("DB_PATH", _default_db)
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", str(ROOT / "data" / "media")))
DEV_BYPASS = os.getenv("DEV_BYPASS", "0") == "1"
DEV_USER_ID = int(os.getenv("DEV_USER_ID", "8764474734"))
DEV_USER_NAME = os.getenv("DEV_USER_NAME", "Slim")
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(50 * 1024 * 1024)))  # 50 MB
YOUTUBE_ENABLED = os.getenv("YOUTUBE_ENABLED", "1") == "1"
# Netscape cookies for yt-dlp. File path wins when it exists; otherwise
# YOUTUBE_COOKIES_B64 is decoded to /tmp/youtube_cookies.txt (see ensure_youtube_cookies).
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
YOUTUBE_COOKIES_B64 = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
YOUTUBE_COOKIES_RUNTIME_PATH = Path("/tmp/youtube_cookies.txt")
YOUTUBE_COOKIES_PATH: Path | None = None


def ensure_youtube_cookies() -> Path | None:
    """Return a Netscape cookies path for yt-dlp, or None.

    Prefer ``YOUTUBE_COOKIES_FILE`` when that file exists and is non-empty.
    Otherwise decode ``YOUTUBE_COOKIES_B64`` and write ``/tmp/youtube_cookies.txt``.
    Never logs cookie contents.
    """
    global YOUTUBE_COOKIES_PATH

    file_env = os.getenv("YOUTUBE_COOKIES_FILE", "").strip() or YOUTUBE_COOKIES_FILE
    b64 = os.getenv("YOUTUBE_COOKIES_B64", "").strip() or YOUTUBE_COOKIES_B64

    if file_env:
        path = Path(file_env).expanduser()
        if path.is_file() and path.stat().st_size > 0:
            YOUTUBE_COOKIES_PATH = path
            return path
        logger.warning("YOUTUBE_COOKIES_FILE is set but missing or empty: %s", path)

    if b64:
        try:
            compact = "".join(b64.split())
            pad = (-len(compact)) % 4
            data = base64.b64decode(compact + ("=" * pad), validate=False)
        except Exception:
            logger.exception("YOUTUBE_COOKIES_B64 is not valid base64")
            YOUTUBE_COOKIES_PATH = None
            return None
        if not data:
            logger.warning("YOUTUBE_COOKIES_B64 decoded to empty cookies")
            YOUTUBE_COOKIES_PATH = None
            return None
        dest = YOUTUBE_COOKIES_RUNTIME_PATH
        dest.write_bytes(data)
        try:
            dest.chmod(0o600)
        except OSError:
            logger.debug("chmod on youtube cookies file failed", exc_info=True)
        YOUTUBE_COOKIES_PATH = dest
        logger.info(
            "Wrote YouTube cookies from YOUTUBE_COOKIES_B64 to %s (%d bytes)",
            dest,
            len(data),
        )
        return dest

    YOUTUBE_COOKIES_PATH = None
    return None
