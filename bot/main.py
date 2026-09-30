"""Thin aiogram bot: /start opens Slim Music WebApp."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BOT_TOKEN = (
    os.getenv("BOT_TOKEN", "").strip()
    or os.getenv("MUSIC_BOT_TOKEN", "").strip()
)
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://127.0.0.1:8001/").strip()
BRAND_NAME = os.getenv("BRAND_NAME", "Slim Music")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slim.bot")


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задано в .env — бот не запуститься")
        sys.exit(1)

    from aiogram import Bot, Dispatcher
    from aiogram.filters import CommandStart
    from aiogram.types import (
        KeyboardButton,
        MenuButtonWebApp,
        Message,
        ReplyKeyboardMarkup,
        WebAppInfo,
    )

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        name = message.from_user.first_name if message.from_user else "Slim"
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text=f"🎵 Відкрити {BRAND_NAME}",
                        web_app=WebAppInfo(url=WEBAPP_URL),
                    )
                ]
            ],
            resize_keyboard=True,
        )
        await message.answer(
            f"Привет, <b>{name}</b>!\n"
            f"Ласкаво просимо до <b>{BRAND_NAME}</b> — музичний каталог.\n"
            "Натисніть кнопку нижче, щоб відкрити застосунок.",
            reply_markup=kb,
            parse_mode="HTML",
        )

    if WEBAPP_URL.startswith("https://"):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Музика",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            )
        except Exception:
            logger.exception("Не вдалося встановити menu button")
    else:
        logger.warning("WEBAPP_URL не HTTPS (%s) — menu button пропущено", WEBAPP_URL)

    me = await bot.get_me()
    logger.info("Bot @%s ready. WEBAPP_URL=%s", me.username, WEBAPP_URL)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
