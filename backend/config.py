from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
APP_NAME = os.getenv("APP_NAME", "LocalStream")

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", BASE_DIR / "media")).resolve()
THUMBNAILS_DIR = Path(os.getenv("THUMBNAILS_DIR", BASE_DIR / "thumbnails")).resolve()
SUBTITLES_DIR = Path(os.getenv("SUBTITLES_DIR", BASE_DIR / "subtitles")).resolve()
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "database" / "localstream.db")).resolve()
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", BASE_DIR / "frontend")).resolve()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
STREAM_PASSWORD = os.getenv("STREAM_PASSWORD", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
STREAM_TOKEN_TTL = int(os.getenv("STREAM_TOKEN_TTL", "43200"))

FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "0"))
STREAM_CHUNK_SIZE = int(os.getenv("STREAM_CHUNK_SIZE", str(1024 * 1024)))
STREAMING_ENABLED_DEFAULT = os.getenv("STREAMING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
