from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from fastapi import HTTPException
from starlette.responses import Response, StreamingResponse

from .config import FFMPEG_PATH, STREAM_CHUNK_SIZE
from .utils import iter_file

logger = logging.getLogger(__name__)


@dataclass
class RangeRequest:
    start: int
    end: int
    total: int


def parse_range_header(range_header: str | None, file_size: int) -> RangeRequest | None:
    if not range_header:
        return None
    units, _, value = range_header.partition("=")
    if units.strip() != "bytes":
        return None
    start_str, _, end_str = value.partition("-")
    try:
        if start_str == "":
            length = int(end_str)
            start = max(file_size - length, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
    except ValueError:
        return None
    if start > end or start < 0:
        return None
    return RangeRequest(start=start, end=min(end, file_size - 1), total=file_size)


def stream_file(path: Path, range_request: RangeRequest | None, media_type: str, on_chunk: Callable[[int], None] | None = None) -> Response:
    file_size = path.stat().st_size
    if range_request:
        start = range_request.start
        end = range_request.end
        content_length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Cache-Control": "public, max-age=3600",
        }
        iterator = _chunk_iterator(path, start, end, on_chunk)
        return StreamingResponse(iterator, status_code=206, headers=headers, media_type=media_type)

    headers = {
        "Content-Length": str(file_size),
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }
    iterator = _chunk_iterator(path, 0, file_size - 1, on_chunk)
    return StreamingResponse(iterator, headers=headers, media_type=media_type)


def _chunk_iterator(path: Path, start: int, end: int, on_chunk: Callable[[int], None] | None = None) -> Iterable[bytes]:
    for data in iter_file(path, start, end, STREAM_CHUNK_SIZE):
        if on_chunk:
            on_chunk(len(data))
        yield data


def transcode_stream(path: Path, on_chunk: Callable[[int], None] | None = None) -> StreamingResponse:
    command = [
        FFMPEG_PATH,
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-f",
        "mp4",
        "-movflags",
        "frag_keyframe+empty_moov",
        "-loglevel",
        "error",
        "pipe:1",
    ]

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        logger.error("Failed to start ffmpeg: %s", exc)
        raise HTTPException(status_code=500, detail="FFmpeg not available") from exc

    def iterator() -> Iterable[bytes]:
        assert process.stdout is not None
        try:
            while True:
                chunk = process.stdout.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                if on_chunk:
                    on_chunk(len(chunk))
                yield chunk
        finally:
            process.stdout.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    return StreamingResponse(iterator(), media_type="video/mp4")


class StreamTracker:
    def __init__(self, session_id: int, update_callback: Callable[[int, bool], None]):
        self.session_id = session_id
        self.update_callback = update_callback
        self.bytes_since = 0
        self.last_flush = time.time()

    def add(self, count: int) -> None:
        self.bytes_since += count
        if self.bytes_since >= 5 * 1024 * 1024 or (time.time() - self.last_flush) > 5:
            self.flush(final=False)

    def flush(self, final: bool) -> None:
        if self.bytes_since:
            self.update_callback(self.bytes_since, final)
        elif final:
            self.update_callback(0, final)
        self.bytes_since = 0
        self.last_flush = time.time()
