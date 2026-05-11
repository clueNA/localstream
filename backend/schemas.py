from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel


class SubtitleTrackOut(BaseModel):
    id: int
    kind: str
    language: str | None = None
    label: str | None = None
    codec: str | None = None

    model_config = {"from_attributes": True}


class MediaOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    category: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    mime_type: str | None = None
    created_at: datetime
    poster_url: str | None = None
    preview_urls: List[str] = []
    stream_url: str | None = None
    subtitle_tracks: List[SubtitleTrackOut] = []

    model_config = {"from_attributes": True}


class MediaUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None


class StreamSessionOut(BaseModel):
    id: int
    media_id: int
    client_ip: str
    user_agent: str | None = None
    started_at: datetime
    last_seen: datetime
    bytes_sent: int
    active: bool

    model_config = {"from_attributes": True}


class ServiceStateOut(BaseModel):
    streaming_enabled: bool
    updated_at: datetime
