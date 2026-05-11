# LocalStream

LocalStream is a lightweight, self-hosted LAN movie streaming platform with a Streamlit admin dashboard and a modern web viewer. Upload videos once, then stream them directly (with HTTP range requests) on any device connected to your local network.

## Features

- **FastAPI backend** with async-friendly streaming and HTTP range support
- **Streamlit dashboard** for uploads, library management, sessions, analytics, and service control
- **Netflix-style viewer** with search, posters, continue-watching, favorites, and subtitles
- **Direct play** for MP4/MKV/AVI/MOV/WEBM with optional FFmpeg fallback transcoding
- **Embedded + external subtitles** (SRT/VTT → WebVTT)
- **Automatic metadata + thumbnails** via FFmpeg/FFprobe
- **SQLite metadata storage**
- **LAN discovery** and QR code for quick mobile access
- **Docker-ready** deployment

## Project Structure

```
/frontend      # Viewer UI (HTML/CSS/JS)
/backend       # FastAPI + Streamlit admin
/media         # Uploaded videos
/thumbnails    # Posters + preview images
/subtitles     # Extracted subtitle tracks
/database      # SQLite database
/docker        # Dockerfile and compose
/scripts       # Startup scripts
```

## Requirements

- Python 3.11+
- FFmpeg + FFprobe available on PATH

## Quick Start (Local)

```bash
cp .env.example .env
python -m pip install -r requirements.txt

# Start FastAPI + Streamlit
# macOS/Linux
./scripts/start.sh

# Windows (PowerShell/CMD)
.\scripts\start.bat
```

- Viewer: `http://<local-ip>:8000`
- Admin: `http://<local-ip>:8501`

## Docker

```bash
cp .env.example .env
cd docker

docker compose up --build
```

## Environment Variables

See `.env.example` for the full list. Common options:

- `STREAM_PASSWORD` – require a password for streaming URLs
- `STREAM_TOKEN_TTL` – token lifetime in seconds for streaming access
- `ADMIN_PASSWORD` – protect the Streamlit dashboard
- `PUBLIC_BASE_URL` – override the base URL shown in the UI
- `MAX_UPLOAD_MB` – hard limit for uploads

## Notes

- For maximum quality playback, LocalStream serves original files directly.
- If a browser can’t play the container/codec, the player automatically requests a transcoded stream.
- Subtitles are converted to WebVTT for browser playback.

## Development

- Backend entry: `backend/app.py`
- Streamlit admin: `backend/admin_app.py`
- Viewer UI: `frontend/index.html` and `frontend/watch.html`
