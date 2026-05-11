from __future__ import annotations

import json
import logging
import mimetypes
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

from .config import (
    FFMPEG_PATH,
    FFPROBE_PATH,
    PORT,
    PUBLIC_BASE_URL,
    STREAM_CHUNK_SIZE,
)

logger = logging.getLogger(__name__)


def ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "media"


def get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def build_public_base_url() -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    return f"http://{get_local_ip()}:{PORT}"


def guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def ffprobe_metadata(file_path: Path) -> dict[str, Any]:
    command = [
        FFPROBE_PATH,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        logger.warning("ffprobe failed for %s: %s", file_path, exc)
        return {
            "duration": None,
            "size_bytes": file_path.stat().st_size if file_path.exists() else None,
            "container": None,
            "video": {},
            "audio": {},
            "subtitles": [],
        }

    format_info = data.get("format", {})
    streams = data.get("streams", [])

    duration = format_info.get("duration")
    duration = float(duration) if duration else None

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    subtitles: list[dict[str, Any]] = []
    for index, stream in enumerate(subtitle_streams):
        tags = stream.get("tags", {})
        subtitles.append(
            {
                "stream_index": stream.get("index"),
                "ffmpeg_index": index,
                "codec": stream.get("codec_name"),
                "language": tags.get("language"),
                "title": tags.get("title") or tags.get("handler_name"),
            }
        )

    size_bytes = int(format_info.get("size")) if format_info.get("size") else None
    if size_bytes is None and file_path.exists():
        size_bytes = file_path.stat().st_size

    return {
        "duration": duration,
        "size_bytes": size_bytes,
        "container": format_info.get("format_name"),
        "video": {
            "codec": video_stream.get("codec_name") if video_stream else None,
            "width": video_stream.get("width") if video_stream else None,
            "height": video_stream.get("height") if video_stream else None,
        },
        "audio": {
            "codec": audio_stream.get("codec_name") if audio_stream else None,
        },
        "subtitles": subtitles,
    }


def pick_poster_timestamp(duration: float | None) -> float:
    if not duration or duration <= 0:
        return 1.0
    return min(5.0, duration / 10)


def generate_poster(file_path: Path, output_path: Path, duration: float | None) -> None:
    timestamp = pick_poster_timestamp(duration)
    command = [
        FFMPEG_PATH,
        "-y",
        "-ss",
        str(timestamp),
        "-i",
        str(file_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=420:-1",
        str(output_path),
    ]
    try:
        subprocess.run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.warning("Poster generation failed for %s: %s", file_path, exc)


def generate_previews(file_path: Path, output_dir: Path, duration: float | None, count: int = 8) -> list[Path]:
    if not duration or duration <= 0:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    fps = min(count / duration, 1.0)
    command = [
        FFMPEG_PATH,
        "-y",
        "-i",
        str(file_path),
        "-vf",
        f"fps={fps},scale=320:-1",
        "-frames:v",
        str(count),
        str(output_dir / "preview_%02d.jpg"),
    ]
    try:
        subprocess.run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        logger.warning("Preview generation failed for %s: %s", file_path, exc)
        return []
    return sorted(output_dir.glob("preview_*.jpg"))


def convert_srt_to_vtt(srt_path: Path, vtt_path: Path) -> None:
    content = srt_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    converted = ["WEBVTT", ""]
    for line in lines:
        if "-->" in line:
            converted.append(line.replace(",", "."))
        else:
            converted.append(line)
    vtt_path.write_text("\n".join(converted), encoding="utf-8")


def iter_file(path: Path, start: int, end: int, chunk_size: int = STREAM_CHUNK_SIZE):
    with path.open("rb") as file_handle:
        file_handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = file_handle.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data
