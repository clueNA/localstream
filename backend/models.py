from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    container: Mapped[str | None] = mapped_column(String(120), nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(120), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    poster_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    subtitle_tracks: Mapped[list[SubtitleTrack]] = relationship(
        "SubtitleTrack",
        back_populates="media",
        cascade="all, delete-orphan",
    )
    stream_sessions: Mapped[list[StreamSession]] = relationship(
        "StreamSession",
        back_populates="media",
        cascade="all, delete-orphan",
    )


class SubtitleTrack(Base):
    __tablename__ = "subtitle_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ffmpeg_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    media: Mapped[Media] = relationship("Media", back_populates="subtitle_tracks")


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id"), nullable=False)
    client_ip: Mapped[str] = mapped_column(String(120), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    bytes_sent: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    media: Mapped[Media] = relationship("Media", back_populates="stream_sessions")


class ServiceState(Base):
    __tablename__ = "service_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    streaming_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
