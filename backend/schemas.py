"""Pydantic schemas for Slim Music API."""
from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class MeOut(BaseModel):
    id: int
    first_name: str
    last_name: str = ""
    username: str = ""
    is_admin: bool = False
    brand_name: str = "Slim Music"
    greeting: str = "Привет, Slim"


class TrackOut(BaseModel):
    id: int
    title: str
    artist: str
    source_type: str  # youtube | mp3 | audio
    source_url: str
    stream_url: str | None = None
    thumbnail_url: str | None = None
    duration_sec: int = 0
    likes_count: int = 0
    plays_count: int = 0
    liked_by_me: bool = False
    added_by: int | None = None
    created_at: str | None = None


class TrackCreate(BaseModel):
    url: str = Field(..., min_length=5, max_length=2000)
    title: str | None = Field(default=None, max_length=300)
    artist: str | None = Field(default=None, max_length=300)


class TrackUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    artist: str | None = Field(default=None, max_length=300)


class StatsOut(BaseModel):
    tracks: int = 0
    playlists: int = 0
    plays: int = 0


class LikeOut(BaseModel):
    liked: bool
    likes_count: int


class PlaylistOut(BaseModel):
    id: int
    name: str
    tracks_count: int = 0
    created_at: str | None = None


class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class PlaylistAddTrack(BaseModel):
    track_id: int
