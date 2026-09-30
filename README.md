# Slim Music — Telegram Mini App

Музичний каталог (темна UI з фіолетовими акцентами, українська/російська).  
Стек: **FastAPI + SQLite (aiosqlite) / Postgres (asyncpg)** · vanilla HTML/CSS/JS · тонкий **aiogram 3** бот.

Бренд: **Slim Music** / SLIM. Бот: `@slim199_bot`.  
**Не** копіює логотипи сторонніх музичних застосунків.

## ⚠️ YouTube / ToS

Завантаження з YouTube через **yt-dlp** може порушувати [умови YouTube](https://www.youtube.com/t/terms).  
Використовуйте лише для **особистого / демо** тестування. У продакшені надавайте перевагу **прямим посиланням на аудіо** (mp3/m4a/ogg/wav). Якщо YouTube увімкнено (`YOUTUBE_ENABLED=1`), yt-dlp часто впирається в bot-check — передайте Netscape cookies (не комітьте файл).

## Структура

```
slim-music-miniapp/
├── backend/          # FastAPI API, auth, media ingest
├── frontend/         # SPA (index.html, styles.css, app.js)
├── bot/              # aiogram: /start + WebApp кнопка
├── data/media/       # локальні аудіофайли
├── Dockerfile
├── Procfile
├── render.yaml
├── .env.example
├── requirements.txt
└── README.md
```

## Швидкий старт (локально)

```bash
cd slim-music-miniapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заповніть BOT_TOKEN (або MUSIC_BOT_TOKEN у середовищі), DEV_BYPASS=1
```

### Backend + фронт

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

Відкрийте http://127.0.0.1:8001/ у браузері (DEV_BYPASS=1 → користувач «Slim»).

Потрібні системні утиліти для тривалості/конвертації: **ffmpeg** / **ffprobe**. Для YouTube — пакет **yt-dlp**.

### Telegram-бот

1. Токен у `.env` → `BOT_TOKEN`.
2. Публічний **HTTPS** URL у `WEBAPP_URL`.
3. `ADMIN_IDS=8764474734` (або ваш Telegram id).
4. `DEV_BYPASS=0` у проді.
5. BotFather: **/setmenubutton** або Mini App → той самий URL.

```bash
python -m bot.main
```

## Можливості (MVP)

1. Auth через Telegram WebApp `initData` (HMAC) або `DEV_BYPASS=1`.
2. Додати трек з URL: пряме аудіо або YouTube (yt-dlp → `data/media` → `/media/...`).
3. Недавно додані / найпопулярніші (за лайками).
4. Лайк (toggle), лічильник прослуховувань при Play.
5. Пошук за назвою/виконавцем.
6. Бібліотека: лайкнуті + додані вами; прості плейлисти.
7. Адмін-редактор: зміна назви/виконавця, видалення.
8. Бот `/start` з кнопкою WebApp.

## API

| Метод | Шлях | Опис |
|-------|------|------|
| GET | `/api/health` | Health |
| GET | `/api/me` | Користувач + бренд |
| GET | `/api/stats` | Треки / плейлисти / прослуховування |
| GET | `/api/tracks/recent` | Недавні |
| GET | `/api/tracks/popular` | Популярні |
| GET | `/api/tracks/search?q=` | Пошук |
| POST | `/api/tracks` | Додати `{url, title?, artist?}` |
| POST | `/api/tracks/{id}/like` | Лайк toggle |
| POST | `/api/tracks/{id}/play` | +1 play |
| PATCH/DELETE | `/api/tracks/{id}` | Адмін |
| GET | `/api/library` | Бібліотека |
| GET/POST | `/api/playlists` | Плейлисти |
| POST | `/api/playlists/{id}/tracks` | Додати трек у плейлист |

Авторизація: заголовок `X-Telegram-Init-Data`. Локально: `DEV_BYPASS=1`.

## Змінні оточення

Див. `.env.example`. Ключові: `BOT_TOKEN`, `ADMIN_IDS`, `WEBAPP_URL`, `DEV_BYPASS`, `DB_PATH`, `MEDIA_DIR`, `YOUTUBE_ENABLED`, `YOUTUBE_COOKIES_FILE`, `YOUTUBE_COOKIES_B64`, `MAX_AUDIO_BYTES`.

### YouTube cookies (bot-check)

На старті, якщо задано `YOUTUBE_COOKIES_B64`, бекенд декодує його в `/tmp/youtube_cookies.txt`. Якщо задано `YOUTUBE_COOKIES_FILE` і файл існує — використовується він (пріоритет вище). Обидва виклики yt-dlp отримують `--cookies`, коли файл є. `YOUTUBE_ENABLED=0` як і раніше вимикає YouTube.

Секрет **не** кладіть у git. На Render (сервіс `slim-music-miniapp`):

```bash
./scripts/encode_youtube_cookies.sh /path/to/cookies.txt
```

Скопіюйте рядок base64 в Environment → `YOUTUBE_COOKIES_B64`. Залиште `YOUTUBE_ENABLED=1`. Після збереження Render перезапустить сервіс.

## Деплой на Render (HTTPS)

1. Завантажте репозиторій / ZIP (без `.env`, `.venv`, великих `data/media`).
2. **New → Blueprint** (`render.yaml`) або Web Service вручну.
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Env: `BOT_TOKEN`, `ADMIN_IDS`, `WEBAPP_URL=https://ВАШ.onrender.com/`, `DEV_BYPASS=0`, `DATABASE_URL` (Internal Postgres), `YOUTUBE_ENABLED=1`, `YOUTUBE_COOKIES_B64` (з cookies.txt, див. скрипт вище — не в репозиторії), `BRAND_NAME=Slim Music`.
6. Оновіть `WEBAPP_URL` після першого деплою → Manual Deploy.
7. BotFather → прив’яжіть HTTPS URL.
8. Окремо запустіть `python -m bot.main` (Worker) або локально з доступом до мережі.

**Примітка:** ephemeral диск на Render не зберігає `data/media` між деплоями — для медіа потрібен зовнішній storage або лише stream URL без локального файлу.

## Ліцензія / відповідальність

Демо для особистого використання. Поважайте авторські права та ToS джерел аудіо.
