from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import psutil
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .config import (
    ADMIN_PASSWORD,
    FRONTEND_DIR,
    PORT,
    STREAM_PASSWORD,
    STREAMING_ENABLED_DEFAULT,
    STREAM_TOKEN_TTL,
)
from .db import SessionLocal, init_db
from .media_service import (
    delete_media,
    ensure_storage,
    get_media,
    get_or_create_service_state,
    list_media,
    save_upload,
    update_media,
)
from .models import StreamSession
from .schemas import (
    MediaOut,
    MediaUpdate,
    ServiceStateOut,
    StreamSessionOut,
    StreamTokenRequest,
    StreamTokenResponse,
    SubtitleTrackOut,
)
from .streaming import StreamTracker, parse_range_header, stream_file, transcode_stream
from .utils import build_public_base_url, get_local_ip, guess_mime_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("localstream")

STREAM_TOKENS: dict[str, datetime] = {}

app = FastAPI(title="LocalStream", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_storage()
    init_db()
    with SessionLocal() as db:
        state = get_or_create_service_state(db)
        if state.streaming_enabled != STREAMING_ENABLED_DEFAULT:
            state.streaming_enabled = STREAMING_ENABLED_DEFAULT
            state.updated_at = datetime.now(timezone.utc)
            db.commit()


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("Frontend not found", status_code=404)


@app.get("/watch", response_class=HTMLResponse)
def watch() -> HTMLResponse:
    watch_path = FRONTEND_DIR / "watch.html"
    if watch_path.exists():
        return HTMLResponse(watch_path.read_text(encoding="utf-8"))
    return HTMLResponse("Watch page not found", status_code=404)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(request: Request) -> None:
    if not ADMIN_PASSWORD:
        return
    token = request.headers.get("X-Admin-Token") or request.query_params.get("admin_token")
    if token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin authentication required")


def require_stream_token(request: Request) -> None:
    if not STREAM_PASSWORD:
        return
    token = request.query_params.get("token") or request.headers.get("X-Stream-Token")
    if not token or not validate_stream_token(token):
        raise HTTPException(status_code=401, detail="Streaming token required")


def issue_stream_token(password: str) -> StreamTokenResponse:
    if password != STREAM_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=STREAM_TOKEN_TTL)
    STREAM_TOKENS[token] = expires_at
    return StreamTokenResponse(token=token, expires_in=STREAM_TOKEN_TTL)


def validate_stream_token(token: str) -> bool:
    expires_at = STREAM_TOKENS.get(token)
    if not expires_at:
        return False
    if expires_at < datetime.now(timezone.utc):
        STREAM_TOKENS.pop(token, None)
        return False
    return True


def serialize_media(media, base_url: str) -> MediaOut:
    subtitle_tracks = [
        SubtitleTrackOut.model_validate(track)
        for track in media.subtitle_tracks
        if track.file_path
    ]
    preview_urls: list[str] = []
    if media.preview_dir:
        preview_path = Path(media.preview_dir)
        if preview_path.exists():
            for item in sorted(preview_path.glob("preview_*.jpg")):
                preview_urls.append(f"{base_url}/api/media/{media.id}/preview/{item.name}")

    poster_url = f"{base_url}/api/media/{media.id}/poster" if media.poster_path else None
    stream_url = f"{base_url}/api/stream/{media.id}"

    return MediaOut(
        id=media.id,
        title=media.title,
        description=media.description,
        category=media.category,
        duration=media.duration,
        width=media.width,
        height=media.height,
        size_bytes=media.size_bytes,
        container=media.container,
        video_codec=media.video_codec,
        audio_codec=media.audio_codec,
        mime_type=media.mime_type,
        created_at=media.created_at,
        poster_url=poster_url,
        preview_urls=preview_urls,
        stream_url=stream_url,
        subtitle_tracks=subtitle_tracks,
    )


@app.get("/api/info")
def info(db: Session = Depends(get_db)) -> dict[str, object]:
    state = get_or_create_service_state(db)
    return {
        "app": "LocalStream",
        "local_ip": get_local_ip(),
        "port": PORT,
        "base_url": build_public_base_url(),
        "stream_password_required": bool(STREAM_PASSWORD),
        "admin_password_required": bool(ADMIN_PASSWORD),
        "streaming_enabled": state.streaming_enabled,
    }


@app.post("/api/auth/token", response_model=StreamTokenResponse)
def api_auth_token(payload: StreamTokenRequest) -> StreamTokenResponse:
    if not STREAM_PASSWORD:
        raise HTTPException(status_code=400, detail="Streaming password not configured")
    return issue_stream_token(payload.password)


@app.get("/api/media", response_model=List[MediaOut])
def api_list_media(db: Session = Depends(get_db)) -> list[MediaOut]:
    base_url = build_public_base_url()
    return [serialize_media(media, base_url) for media in list_media(db)]


@app.get("/api/media/{media_id}", response_model=MediaOut)
def api_get_media(media_id: int, db: Session = Depends(get_db)) -> MediaOut:
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return serialize_media(media, build_public_base_url())


@app.patch("/api/media/{media_id}", response_model=MediaOut)
def api_update_media(
    media_id: int,
    payload: MediaUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> MediaOut:
    require_admin(request)
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    update_media(db, media, payload.title, payload.description, payload.category)
    return serialize_media(media, build_public_base_url())


@app.delete("/api/media/{media_id}")
def api_delete_media(media_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    require_admin(request)
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    delete_media(db, media)
    return {"status": "deleted"}


@app.post("/api/upload", response_model=List[MediaOut])
def api_upload(request: Request, files: List[UploadFile] = File(...), db: Session = Depends(get_db)) -> list[MediaOut]:
    require_admin(request)
    base_url = build_public_base_url()
    uploaded: list[MediaOut] = []
    for upload in files:
        try:
            media = save_upload(upload, db)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        uploaded.append(serialize_media(media, base_url))
    return uploaded


@app.get("/api/media/{media_id}/poster")
def api_poster(media_id: int, db: Session = Depends(get_db)) -> FileResponse:
    media = get_media(db, media_id)
    if not media or not media.poster_path:
        raise HTTPException(status_code=404, detail="Poster not found")
    return FileResponse(media.poster_path, media_type="image/jpeg")


@app.get("/api/media/{media_id}/preview/{filename}")
def api_preview(media_id: int, filename: str, db: Session = Depends(get_db)) -> FileResponse:
    media = get_media(db, media_id)
    if not media or not media.preview_dir:
        raise HTTPException(status_code=404, detail="Preview not found")
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid preview name")
    preview_dir = Path(media.preview_dir).resolve()
    preview_path = (preview_dir / filename).resolve()
    if preview_dir not in preview_path.parents:
        raise HTTPException(status_code=400, detail="Invalid preview path")
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path, media_type="image/jpeg")


@app.get("/api/media/{media_id}/subtitle-tracks")
def api_subtitle_tracks(media_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    tracks = [
        SubtitleTrackOut.model_validate(track)
        for track in media.subtitle_tracks
        if track.file_path
    ]
    return {"tracks": tracks}


@app.get("/api/media/{media_id}/subtitles/{track_id}")
def api_subtitle_file(media_id: int, track_id: int, request: Request, db: Session = Depends(get_db)) -> FileResponse:
    require_stream_token(request)
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    track = next((track for track in media.subtitle_tracks if track.id == track_id), None)
    if not track:
        raise HTTPException(status_code=404, detail="Subtitle track not found")
    if not track.file_path:
        # Embedded subtitles require extraction at upload time
        raise HTTPException(status_code=404, detail="Subtitle file not ready")
    if not Path(track.file_path).exists():
        raise HTTPException(status_code=404, detail="Subtitle file missing")
    return FileResponse(track.file_path, media_type="text/vtt")


def create_stream_session(db: Session, media_id: int, client_ip: str, user_agent: str | None) -> int:
    session = StreamSession(
        media_id=media_id,
        client_ip=client_ip,
        user_agent=user_agent,
        active=True,
        started_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        bytes_sent=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session.id


def update_session_bytes(session_id: int, bytes_sent: int, final: bool) -> None:
    with SessionLocal() as db:
        session = db.get(StreamSession, session_id)
        if not session:
            return
        session.bytes_sent += bytes_sent
        session.last_seen = datetime.now(timezone.utc)
        if final:
            session.active = False
        db.commit()


@app.get("/api/stream/{media_id}")
def api_stream(media_id: int, request: Request, transcode: bool = False, db: Session = Depends(get_db)):
    require_stream_token(request)
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    state = get_or_create_service_state(db)
    if not state.streaming_enabled:
        raise HTTPException(status_code=503, detail="Streaming service disabled")

    file_path = Path(media.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file missing")

    session_id = create_stream_session(
        db,
        media.id,
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent"),
    )
    tracker = StreamTracker(session_id, lambda bytes_sent, final: update_session_bytes(session_id, bytes_sent, final))

    if transcode:
        response = transcode_stream(file_path, tracker.add)
        response.background = BackgroundTask(tracker.flush, final=True)
        return response

    range_header = request.headers.get("range")
    range_request = parse_range_header(range_header, file_path.stat().st_size)
    response = stream_file(file_path, range_request, media.mime_type or guess_mime_type(file_path), tracker.add)
    response.background = BackgroundTask(tracker.flush, final=True)
    return response


@app.get("/api/service/status", response_model=ServiceStateOut)
def api_service_status(db: Session = Depends(get_db)) -> ServiceStateOut:
    state = get_or_create_service_state(db)
    return ServiceStateOut(streaming_enabled=state.streaming_enabled, updated_at=state.updated_at)


@app.post("/api/service/start", response_model=ServiceStateOut)
def api_service_start(request: Request, db: Session = Depends(get_db)) -> ServiceStateOut:
    require_admin(request)
    state = get_or_create_service_state(db)
    state.streaming_enabled = True
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ServiceStateOut(streaming_enabled=state.streaming_enabled, updated_at=state.updated_at)


@app.post("/api/service/stop", response_model=ServiceStateOut)
def api_service_stop(request: Request, db: Session = Depends(get_db)) -> ServiceStateOut:
    require_admin(request)
    state = get_or_create_service_state(db)
    state.streaming_enabled = False
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ServiceStateOut(streaming_enabled=state.streaming_enabled, updated_at=state.updated_at)


@app.get("/api/sessions", response_model=List[StreamSessionOut])
def api_sessions(db: Session = Depends(get_db)) -> list[StreamSessionOut]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    sessions = (
        db.query(StreamSession)
        .filter(StreamSession.last_seen >= cutoff, StreamSession.active.is_(True))
        .order_by(StreamSession.last_seen.desc())
        .all()
    )
    return [StreamSessionOut.model_validate(session) for session in sessions]


@app.delete("/api/sessions/{session_id}")
def api_terminate_session(session_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    require_admin(request)
    session = db.get(StreamSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.active = False
    session.last_seen = datetime.now(timezone.utc)
    db.commit()
    return {"status": "terminated"}


@app.get("/api/network")
def api_network() -> dict[str, object]:
    counters = psutil.net_io_counters()
    return {
        "local_ip": get_local_ip(),
        "bytes_sent": counters.bytes_sent,
        "bytes_recv": counters.bytes_recv,
        "packets_sent": counters.packets_sent,
        "packets_recv": counters.packets_recv,
    }


@app.get("/api/media/{media_id}/file")
def api_media_file(media_id: int, request: Request, db: Session = Depends(get_db)) -> FileResponse:
    require_stream_token(request)
    media = get_media(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return FileResponse(media.file_path, filename=media.filename)


@app.get("/api/media/{media_id}/download")
def api_media_download(media_id: int, request: Request, db: Session = Depends(get_db)) -> FileResponse:
    return api_media_file(media_id, request, db)


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
