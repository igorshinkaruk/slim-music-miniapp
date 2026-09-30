"""Application configuration from environment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

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
