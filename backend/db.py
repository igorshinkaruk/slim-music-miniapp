"""DB helpers: Postgres (asyncpg) when DATABASE_URL is set, else SQLite (aiosqlite)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from . import config

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    stream_url TEXT,
    local_path TEXT,
    thumbnail_url TEXT,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    likes_count INTEGER NOT NULL DEFAULT 0,
    plays_count INTEGER NOT NULL DEFAULT 0,
    added_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, track_id),
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tracks_likes ON tracks(likes_count DESC);
CREATE INDEX IF NOT EXISTS idx_likes_user ON likes(user_id);
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS tracks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    stream_url TEXT,
    local_path TEXT,
    thumbnail_url TEXT,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    likes_count INTEGER NOT NULL DEFAULT 0,
    plays_count INTEGER NOT NULL DEFAULT 0,
    added_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS likes (
    user_id BIGINT NOT NULL,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, track_id)
);

CREATE TABLE IF NOT EXISTS playlists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (playlist_id, track_id)
);

CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tracks_likes ON tracks(likes_count DESC);
CREATE INDEX IF NOT EXISTS idx_likes_user ON likes(user_id);
"""


def use_postgres() -> bool:
    return bool(config.DATABASE_URL)


def _qmark_to_dollar(sql: str) -> str:
    parts: list[str] = []
    n = 0
    for ch in sql:
        if ch == "?":
            n += 1
            parts.append(f"${n}")
        else:
            parts.append(ch)
    return "".join(parts)


def _adapt_sql(sql: str) -> str:
    s = sql.strip()
    if s.upper().startswith("INSERT OR IGNORE INTO"):
        s = "INSERT INTO" + s[len("INSERT OR IGNORE INTO") :]
        if "ON CONFLICT" not in s.upper():
            s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return _qmark_to_dollar(s)


class _Row(dict):
    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, rows: list[_Row] | None = None, lastrowid: int | None = None):
        self._rows = rows or []
        self.lastrowid = lastrowid

    async def fetchall(self) -> list[_Row]:
        return self._rows

    async def fetchone(self) -> _Row | None:
        return self._rows[0] if self._rows else None


class _PgConn:
    def __init__(self, conn: Any):
        self._conn = conn
        self.lastrowid: int | None = None

    async def execute(self, sql: str, params: Sequence[Any] | None = None) -> _Cursor:
        params = tuple(params or ())
        adapted = _adapt_sql(sql)
        upper = sql.strip().upper()
        if upper.startswith("INSERT") and "RETURNING" not in upper:
            adapted_ret = adapted.rstrip().rstrip(";") + " RETURNING id"
            try:
                row = await self._conn.fetchrow(adapted_ret, *params)
                rid = int(row["id"]) if row else None
                self.lastrowid = rid
                return _Cursor(lastrowid=rid)
            except Exception:
                await self._conn.execute(adapted, *params)
                self.lastrowid = None
                return _Cursor(lastrowid=None)
        if upper.startswith("SELECT") or upper.startswith("WITH"):
            records = await self._conn.fetch(adapted, *params)
            rows = [_Row(dict(r)) for r in records]
            return _Cursor(rows=rows)
        await self._conn.execute(adapted, *params)
        return _Cursor()

    async def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> None:
        adapted = _adapt_sql(sql)
        await self._conn.executemany(adapted, list(seq_of_params))

    async def executescript(self, script: str) -> None:
        parts = [s.strip() for s in script.split(";") if s.strip()]
        for part in parts:
            await self._conn.execute(part)

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        await self._conn.close()


class _SqliteConn:
    def __init__(self, conn: Any):
        self._conn = conn
        self.lastrowid: int | None = None

    async def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        cur = await self._conn.execute(sql, params or ())
        self.lastrowid = cur.lastrowid
        return cur

    async def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> Any:
        return await self._conn.executemany(sql, seq_of_params)

    async def executescript(self, script: str) -> Any:
        return await self._conn.executescript(script)

    async def commit(self) -> None:
        await self._conn.commit()

    async def close(self) -> None:
        await self._conn.close()


async def get_db():
    if use_postgres():
        import ssl

        import asyncpg

        url = config.DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = await asyncpg.connect(url, ssl=ctx)
        return _PgConn(raw)

    import aiosqlite

    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    raw = await aiosqlite.connect(config.DB_PATH)
    raw.row_factory = aiosqlite.Row
    await raw.execute("PRAGMA foreign_keys = ON")
    return _SqliteConn(raw)


async def init_db() -> None:
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    if use_postgres():
        db = await get_db()
        try:
            await db.executescript(SCHEMA_PG)
        finally:
            await db.close()
        return

    import aiosqlite

    async with aiosqlite.connect(config.DB_PATH) as raw:
        await raw.executescript(SCHEMA_SQLITE)
        await raw.commit()
