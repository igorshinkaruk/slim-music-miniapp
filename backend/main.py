"""Slim Music Mini App — FastAPI backend."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .auth import get_current_user
from .db import get_db, init_db
from .media import ingest_url
from .schemas import (
    LikeOut,
    MeOut,
    PlaylistAddTrack,
    PlaylistCreate,
    PlaylistOut,
    StatsOut,
    TrackCreate,
    TrackOut,
    TrackUpdate,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slim")

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title=f"{config.BRAND_NAME} API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Started %s (DEV_BYPASS=%s, MEDIA=%s)",
        config.BRAND_NAME,
        config.DEV_BYPASS,
        config.MEDIA_DIR,
    )


def _row_to_track(row: Any, liked_ids: set[int] | None = None) -> TrackOut:
    d = dict(row)
    tid = int(d["id"])
    stream = d.get("stream_url") or None
    local = d.get("local_path")
    if local and not stream:
        stream = f"/media/{Path(local).name}"
    return TrackOut(
        id=tid,
        title=d["title"],
        artist=d.get("artist") or "",
        source_type=d["source_type"],
        source_url=d["source_url"],
        stream_url=stream,
        thumbnail_url=d.get("thumbnail_url"),
        duration_sec=int(d.get("duration_sec") or 0),
        likes_count=int(d.get("likes_count") or 0),
        plays_count=int(d.get("plays_count") or 0),
        liked_by_me=tid in (liked_ids or set()),
        added_by=d.get("added_by"),
        created_at=str(d["created_at"]) if d.get("created_at") is not None else None,
    )


async def _liked_set(db, user_id: int) -> set[int]:
    cur = await db.execute("SELECT track_id FROM likes WHERE user_id = ?", (user_id,))
    rows = await cur.fetchall()
    return {int(r["track_id"]) for r in rows}


@app.get("/api/health")
async def health():
    return {"ok": True, "brand": config.BRAND_NAME}


@app.get("/api/me", response_model=MeOut)
async def me(user=Depends(get_current_user)):
    name = user.get("first_name") or "Slim"
    return MeOut(
        id=user["id"],
        first_name=name,
        last_name=user.get("last_name") or "",
        username=user.get("username") or "",
        is_admin=bool(user.get("is_admin")),
        brand_name=config.BRAND_NAME,
        greeting=f"Привет, {name}",
    )


@app.get("/api/stats", response_model=StatsOut)
async def stats(user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) AS c FROM tracks")
        row = await cur.fetchone()
        tracks = int(row["c"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])
        cur = await db.execute("SELECT COALESCE(SUM(plays_count), 0) AS s FROM tracks")
        row = await cur.fetchone()
        plays = int(row["s"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])
        cur = await db.execute("SELECT COUNT(*) AS c FROM playlists")
        row = await cur.fetchone()
        playlists = int(row["c"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])
        return StatsOut(tracks=tracks, playlists=playlists, plays=plays)
    finally:
        await db.close()


@app.get("/api/tracks/recent", response_model=list[TrackOut])
async def tracks_recent(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    db = await get_db()
    try:
        liked = await _liked_set(db, user["id"])
        cur = await db.execute(
            "SELECT * FROM tracks ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [_row_to_track(r, liked) for r in rows]
    finally:
        await db.close()


@app.get("/api/tracks/popular", response_model=list[TrackOut])
async def tracks_popular(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    db = await get_db()
    try:
        liked = await _liked_set(db, user["id"])
        cur = await db.execute(
            "SELECT * FROM tracks ORDER BY likes_count DESC, plays_count DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [_row_to_track(r, liked) for r in rows]
    finally:
        await db.close()


@app.get("/api/tracks/search", response_model=list[TrackOut])
async def tracks_search(q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=100), user=Depends(get_current_user)):
    q = q.strip()
    db = await get_db()
    try:
        liked = await _liked_set(db, user["id"])
        if not q:
            return []
        like = f"%{q}%"
        cur = await db.execute(
            "SELECT * FROM tracks WHERE title LIKE ? OR artist LIKE ? "
            "ORDER BY likes_count DESC, id DESC LIMIT ?",
            (like, like, limit),
        )
        rows = await cur.fetchall()
        return [_row_to_track(r, liked) for r in rows]
    finally:
        await db.close()


@app.get("/api/tracks/{track_id}", response_model=TrackOut)
async def track_get(track_id: int, user=Depends(get_current_user)):
    db = await get_db()
    try:
        liked = await _liked_set(db, user["id"])
        cur = await db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Трек не знайдено")
        return _row_to_track(row, liked)
    finally:
        await db.close()


@app.post("/api/tracks", response_model=TrackOut)
async def track_create(body: TrackCreate, user=Depends(get_current_user)):
    try:
        meta = await ingest_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("ingest failed")
        raise HTTPException(400, f"Не вдалося додати трек: {e}") from e

    title = (body.title or meta["title"] or "Без назви").strip()[:300]
    artist = (body.artist if body.artist is not None else meta.get("artist") or "").strip()[:300]

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO tracks (title, artist, source_type, source_url, stream_url, local_path, "
            "thumbnail_url, duration_sec, added_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                artist,
                meta["source_type"],
                meta["source_url"],
                meta.get("stream_url"),
                meta.get("local_path"),
                meta.get("thumbnail_url"),
                int(meta.get("duration_sec") or 0),
                user["id"],
            ),
        )
        await db.commit()
        tid = db.lastrowid
        cur = await db.execute("SELECT * FROM tracks WHERE id = ?", (tid,))
        row = await cur.fetchone()
        return _row_to_track(row, set())
    finally:
        await db.close()


@app.patch("/api/tracks/{track_id}", response_model=TrackOut)
async def track_update(track_id: int, body: TrackUpdate, user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Лише адмін")
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Трек не знайдено")
        title = body.title if body.title is not None else row["title"]
        artist = body.artist if body.artist is not None else row["artist"]
        await db.execute(
            "UPDATE tracks SET title = ?, artist = ? WHERE id = ?",
            (title.strip()[:300], (artist or "").strip()[:300], track_id),
        )
        await db.commit()
        liked = await _liked_set(db, user["id"])
        cur = await db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        return _row_to_track(await cur.fetchone(), liked)
    finally:
        await db.close()


@app.delete("/api/tracks/{track_id}")
async def track_delete(track_id: int, user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Лише адмін")
    db = await get_db()
    try:
        cur = await db.execute("SELECT local_path FROM tracks WHERE id = ?", (track_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Трек не знайдено")
        local = row["local_path"]
        await db.execute("DELETE FROM likes WHERE track_id = ?", (track_id,))
        await db.execute("DELETE FROM playlist_tracks WHERE track_id = ?", (track_id,))
        await db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        await db.commit()
        if local:
            p = Path(local)
            if p.exists() and config.MEDIA_DIR.resolve() in p.resolve().parents:
                p.unlink(missing_ok=True)
        return {"ok": True}
    finally:
        await db.close()


@app.post("/api/tracks/{track_id}/like", response_model=LikeOut)
async def track_like(track_id: int, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id, likes_count FROM tracks WHERE id = ?", (track_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Трек не знайдено")
        cur = await db.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND track_id = ?",
            (user["id"], track_id),
        )
        exists = await cur.fetchone()
        if exists:
            await db.execute(
                "DELETE FROM likes WHERE user_id = ? AND track_id = ?",
                (user["id"], track_id),
            )
            await db.execute(
                "UPDATE tracks SET likes_count = CASE WHEN likes_count > 0 THEN likes_count - 1 ELSE 0 END WHERE id = ?",
                (track_id,),
            )
            liked = False
        else:
            await db.execute(
                "INSERT OR IGNORE INTO likes (user_id, track_id) VALUES (?, ?)",
                (user["id"], track_id),
            )
            await db.execute(
                "UPDATE tracks SET likes_count = likes_count + 1 WHERE id = ?",
                (track_id,),
            )
            liked = True
        await db.commit()
        cur = await db.execute("SELECT likes_count FROM tracks WHERE id = ?", (track_id,))
        row = await cur.fetchone()
        return LikeOut(liked=liked, likes_count=int(row["likes_count"]))
    finally:
        await db.close()


@app.post("/api/tracks/{track_id}/play")
async def track_play(track_id: int, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM tracks WHERE id = ?", (track_id,))
        if not await cur.fetchone():
            raise HTTPException(404, "Трек не знайдено")
        await db.execute(
            "UPDATE tracks SET plays_count = plays_count + 1 WHERE id = ?",
            (track_id,),
        )
        await db.commit()
        cur = await db.execute("SELECT plays_count FROM tracks WHERE id = ?", (track_id,))
        row = await cur.fetchone()
        return {"ok": True, "plays_count": int(row["plays_count"])}
    finally:
        await db.close()


@app.get("/api/library", response_model=list[TrackOut])
async def library(user=Depends(get_current_user)):
    """Liked tracks + tracks added by me."""
    db = await get_db()
    try:
        liked = await _liked_set(db, user["id"])
        cur = await db.execute(
            "SELECT DISTINCT t.* FROM tracks t "
            "LEFT JOIN likes l ON l.track_id = t.id AND l.user_id = ? "
            "WHERE l.user_id IS NOT NULL OR t.added_by = ? "
            "ORDER BY t.created_at DESC",
            (user["id"], user["id"]),
        )
        rows = await cur.fetchall()
        return [_row_to_track(r, liked) for r in rows]
    finally:
        await db.close()


@app.get("/api/playlists", response_model=list[PlaylistOut])
async def playlists_list(user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT p.id, p.name, p.created_at, "
            "(SELECT COUNT(*) FROM playlist_tracks pt WHERE pt.playlist_id = p.id) AS tracks_count "
            "FROM playlists p WHERE p.owner_id = ? ORDER BY p.id DESC",
            (user["id"],),
        )
        rows = await cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            ca = d.get("created_at")
            out.append(
                PlaylistOut(
                    id=int(d["id"]),
                    name=d["name"],
                    tracks_count=int(d.get("tracks_count") or 0),
                    created_at=str(ca) if ca is not None else None,
                )
            )
        return out
    finally:
        await db.close()


@app.post("/api/playlists", response_model=PlaylistOut)
async def playlists_create(body: PlaylistCreate, user=Depends(get_current_user)):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO playlists (name, owner_id) VALUES (?, ?)",
            (body.name.strip()[:120], user["id"]),
        )
        await db.commit()
        pid = db.lastrowid
        return PlaylistOut(id=int(pid), name=body.name.strip()[:120], tracks_count=0)
    finally:
        await db.close()


@app.post("/api/playlists/{playlist_id}/tracks")
async def playlists_add_track(playlist_id: int, body: PlaylistAddTrack, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id FROM playlists WHERE id = ? AND owner_id = ?",
            (playlist_id, user["id"]),
        )
        if not await cur.fetchone():
            raise HTTPException(404, "Плейлист не знайдено")
        cur = await db.execute("SELECT id FROM tracks WHERE id = ?", (body.track_id,))
        if not await cur.fetchone():
            raise HTTPException(404, "Трек не знайдено")
        await db.execute(
            "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id) VALUES (?, ?)",
            (playlist_id, body.track_id),
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@app.get("/api/playlists/{playlist_id}/tracks", response_model=list[TrackOut])
async def playlists_tracks(playlist_id: int, user=Depends(get_current_user)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id FROM playlists WHERE id = ? AND owner_id = ?",
            (playlist_id, user["id"]),
        )
        if not await cur.fetchone():
            raise HTTPException(404, "Плейлист не знайдено")
        liked = await _liked_set(db, user["id"])
        cur = await db.execute(
            "SELECT t.* FROM tracks t "
            "JOIN playlist_tracks pt ON pt.track_id = t.id "
            "WHERE pt.playlist_id = ? ORDER BY pt.position, t.id",
            (playlist_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_track(r, liked) for r in rows]
    finally:
        await db.close()


# Static media + frontend
config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(config.MEDIA_DIR)), name="media")


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/styles.css")
async def styles():
    return FileResponse(FRONTEND / "styles.css", media_type="text/css")


@app.get("/app.js")
async def app_js():
    return FileResponse(FRONTEND / "app.js", media_type="application/javascript")


@app.get("/telegram-web-app.js")
async def tg_js():
    return FileResponse(FRONTEND / "telegram-web-app.js", media_type="application/javascript")
