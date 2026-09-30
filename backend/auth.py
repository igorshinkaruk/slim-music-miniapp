"""Telegram WebApp initData validation."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from . import config


def _parse_init_data(init_data: str) -> dict[str, str]:
    return dict(parse_qsl(init_data, keep_blank_values=True))


def validate_webapp_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict[str, Any]:
    """Validate Telegram WebApp initData per Bot API docs. Returns user dict."""
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing initData")

    parsed = _parse_init_data(init_data)
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    auth_date = int(parsed.get("auth_date", "0"))
    if max_age and auth_date and (time.time() - auth_date) > max_age:
        raise HTTPException(status_code=401, detail="initData expired")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="No user in initData")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=401, detail="Bad user JSON") from e
    return user


async def get_current_user(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    """Dependency: validated Telegram user or DEV_BYPASS stub."""
    if config.BOT_TOKEN and x_telegram_init_data:
        user = validate_webapp_init_data(x_telegram_init_data, config.BOT_TOKEN)
        return {
            "id": int(user["id"]),
            "first_name": user.get("first_name") or "",
            "last_name": user.get("last_name") or "",
            "username": user.get("username") or "",
            "is_admin": int(user["id"]) in config.ADMIN_IDS,
        }

    if config.DEV_BYPASS:
        return {
            "id": config.DEV_USER_ID,
            "first_name": config.DEV_USER_NAME.split()[0] if config.DEV_USER_NAME else "Slim",
            "last_name": " ".join(config.DEV_USER_NAME.split()[1:]) if config.DEV_USER_NAME else "",
            "username": "slim",
            "is_admin": True,
        }

    raise HTTPException(
        status_code=401,
        detail="Telegram auth required (set BOT_TOKEN + initData, or DEV_BYPASS=1)",
    )
