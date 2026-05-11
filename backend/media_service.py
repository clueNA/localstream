from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sqlalchemy.orm import Session

from .config import ALLOWED_EXTENSIONS, FFMPEG_PATH, MAX_UPLOAD_MB, MEDIA_DIR, SUBTITLES_DIR, THUMBNAILS_DIR
from .models import Media, ServiceState, SubtitleTrack
from .utils import (
    convert_srt_to_vtt,
    ensure_directories,
    ffprobe_metadata,
    generate_poster,
    generate_previews,
    guess_mime_type,
    safe_filename,
)

logger = logging.getLogger(__name__)


def ensure_storage() -> None:
    ensure_directories(MEDIA_DIR, THUMBNAILS_DIR, SUBTITLES_DIR)


def get_or_create_service_state(db: Session) -> ServiceState:
    state = db.query(ServiceState).first()
    if state:
        return state
    state = ServiceState(streaming_enabled=True)
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _write_upload_file(upload_file, destination: Path) -> int:
    total = 0
    with destination.open("wb") as file_handle:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if MAX_UPLOAD_MB and total > MAX_UPLOAD_MB * 1024 * 1024:
                raise ValueError("Upload exceeds MAX_UPLOAD_MB")
            file_handle.write(chunk)
    return total


def _external_subtitle_candidates(media_path: Path) -> Iterable[Path]:
    for extension in (".srt", ".vtt"):
        candidate = media_path.with_suffix(extension)
        if candidate.exists():
            yield candidate


def _extract_embedded_subtitle(media_path: Path, media_id: int, ffmpeg_index: int | None) -> Path | None:
    if ffmpeg_index is None:
        return None
    output_path = SUBTITLES_DIR / f"{media_id}-embedded-{ffmpeg_index}.vtt"
    command = [
        FFMPEG_PATH,
        "-y",
        "-i",
        str(media_path),
        "-map",
        f"0:s:{ffmpeg_index}",
        "-c:s",
        "webvtt",
        str(output_path),
    ]
    try:
        subprocess.run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.warning("Failed to extract embedded subtitle: %s", exc)
        return None
    return output_path if output_path.exists() else None


def save_upload(upload_file, db: Session) -> Media:
    ensure_storage()
    original_name = Path(upload_file.filename or "media")
    extension = original_name.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension}")

    safe_stem = safe_filename(original_name.stem)
    unique_name = f"{safe_stem}-{uuid4().hex[:8]}{extension}"
    file_path = MEDIA_DIR / unique_name

    try:
        size_bytes = _write_upload_file(upload_file, file_path)
    except Exception:
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        raise
    finally:
        try:
            upload_file.file.close()
        except Exception:
            pass

    metadata = ffprobe_metadata(file_path)
    title = safe_stem.replace("_", " ").strip() or file_path.stem

    media = Media(
        filename=unique_name,
        file_path=str(file_path),
        title=title,
        duration=metadata.get("duration"),
        width=metadata.get("video", {}).get("width"),
        height=metadata.get("video", {}).get("height"),
        size_bytes=size_bytes,
        container=metadata.get("container"),
        video_codec=metadata.get("video", {}).get("codec"),
        audio_codec=metadata.get("audio", {}).get("codec"),
        mime_type=guess_mime_type(file_path),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    poster_path = THUMBNAILS_DIR / f"{media.id}.jpg"
    generate_poster(file_path, poster_path, metadata.get("duration"))

    preview_dir = THUMBNAILS_DIR / f"{media.id}"
    previews = generate_previews(file_path, preview_dir, metadata.get("duration"))

    media.poster_path = str(poster_path) if poster_path.exists() else None
    media.preview_dir = str(preview_dir) if previews else None
    media.updated_at = datetime.now(timezone.utc)

    subtitle_tracks: list[SubtitleTrack] = []
    for subtitle in metadata.get("subtitles", []):
        extracted = _extract_embedded_subtitle(file_path, media.id, subtitle.get("ffmpeg_index"))
        subtitle_tracks.append(
            SubtitleTrack(
                media_id=media.id,
                kind="embedded",
                language=subtitle.get("language"),
                label=subtitle.get("title"),
                codec=subtitle.get("codec"),
                ffmpeg_index=subtitle.get("ffmpeg_index"),
                file_path=str(extracted) if extracted else None,
            )
        )

    for external in _external_subtitle_candidates(file_path):
        vtt_path = SUBTITLES_DIR / f"{media.id}-{external.stem}.vtt"
        if external.suffix.lower() == ".vtt":
            shutil.copy(external, vtt_path)
        else:
            convert_srt_to_vtt(external, vtt_path)
        subtitle_tracks.append(
            SubtitleTrack(
                media_id=media.id,
                kind="external",
                language=None,
                label=external.stem,
                codec="vtt",
                file_path=str(vtt_path),
            )
        )

    if subtitle_tracks:
        db.add_all(subtitle_tracks)

    db.commit()
    db.refresh(media)
    return media


def list_media(db: Session) -> list[Media]:
    return db.query(Media).order_by(Media.created_at.desc()).all()


def get_media(db: Session, media_id: int) -> Media | None:
    return db.query(Media).filter(Media.id == media_id).first()


def update_media(db: Session, media: Media, title: str | None, description: str | None, category: str | None) -> Media:
    if title is not None:
        media.title = title
    if description is not None:
        media.description = description
    if category is not None:
        media.category = category
    media.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(media)
    return media


def delete_media(db: Session, media: Media) -> None:
    try:
        if media.file_path:
            Path(media.file_path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to delete media file: %s", exc)

    if media.poster_path:
        Path(media.poster_path).unlink(missing_ok=True)
    if media.preview_dir:
        shutil.rmtree(media.preview_dir, ignore_errors=True)

    for track in media.subtitle_tracks:
        if track.file_path:
            Path(track.file_path).unlink(missing_ok=True)

    db.delete(media)
    db.commit()
