from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO

import psutil
import qrcode
import streamlit as st

from .config import ADMIN_PASSWORD, PORT
from .db import SessionLocal, init_db
from .media_service import (
    delete_media,
    ensure_storage,
    get_or_create_service_state,
    list_media,
    save_upload,
    update_media,
)
from .models import StreamSession
from .utils import build_public_base_url, get_local_ip

st.set_page_config(page_title="LocalStream Admin", layout="wide")


def format_bytes(num: int | float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def require_auth() -> None:
    if not ADMIN_PASSWORD:
        return
    if st.session_state.get("authenticated"):
        return
    st.title("LocalStream Admin Login")
    password = st.text_input("Admin password", type="password")
    if st.button("Unlock"):
        if password == ADMIN_PASSWORD:
            st.session_state["authenticated"] = True
            st.experimental_rerun()
        else:
            st.error("Invalid password")
    st.stop()


init_db()
ensure_storage()
require_auth()

with SessionLocal() as db:
    state = get_or_create_service_state(db)

    st.title("LocalStream Admin Dashboard")
    base_url = build_public_base_url()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Local IP", get_local_ip())
    with col2:
        st.metric("Streaming Port", PORT)
    with col3:
        st.metric("Base URL", base_url)

    qr = qrcode.QRCode(box_size=2, border=2)
    qr.add_data(base_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    st.image(buffer.getvalue(), caption="Scan to open the viewer")

    st.subheader("Service Control")
    streaming_enabled = st.toggle("Streaming enabled", value=state.streaming_enabled)
    if streaming_enabled != state.streaming_enabled:
        state.streaming_enabled = streaming_enabled
        state.updated_at = datetime.utcnow()
        db.commit()

    tabs = st.tabs(["Upload", "Library", "Streams", "Analytics"])

    with tabs[0]:
        st.subheader("Upload Media")
        uploads = st.file_uploader(
            "Select videos",
            type=["mp4", "mkv", "avi", "mov", "webm"],
            accept_multiple_files=True,
        )
        if st.button("Upload", disabled=not uploads):
            for item in uploads or []:
                item.seek(0)
                wrapper = type("Upload", (), {"filename": item.name, "file": item})
                try:
                    save_upload(wrapper, db)
                    st.success(f"Uploaded {item.name}")
                except Exception as exc:
                    st.error(f"Failed to upload {item.name}: {exc}")

    with tabs[1]:
        st.subheader("Media Library")
        media_items = list_media(db)
        if not media_items:
            st.info("No media uploaded yet.")
        for media in media_items:
            with st.expander(f"{media.title} ({media.id})"):
                st.write(f"Duration: {media.duration or 0:.1f}s")
                st.write(f"Resolution: {media.width or '-'} x {media.height or '-'}")
                if media.poster_path:
                    st.image(media.poster_path, width=200)
                new_title = st.text_input("Title", value=media.title, key=f"title-{media.id}")
                new_category = st.text_input(
                    "Category", value=media.category or "", key=f"cat-{media.id}"
                )
                new_desc = st.text_area(
                    "Description", value=media.description or "", key=f"desc-{media.id}"
                )
                cols = st.columns(2)
                if cols[0].button("Save", key=f"save-{media.id}"):
                    update_media(db, media, new_title, new_desc, new_category)
                    st.success("Updated")
                if cols[1].button("Delete", key=f"delete-{media.id}"):
                    delete_media(db, media)
                    st.success("Deleted")
                    st.experimental_rerun()

    with tabs[2]:
        st.subheader("Active Streams")
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        sessions = (
            db.query(StreamSession)
            .filter(StreamSession.last_seen >= cutoff, StreamSession.active.is_(True))
            .order_by(StreamSession.last_seen.desc())
            .all()
        )
        if not sessions:
            st.info("No active streams")
        else:
            for session in sessions:
                cols = st.columns([4, 1])
                cols[0].write(
                    f"Media #{session.media_id} | {session.client_ip} | "
                    f"{format_bytes(session.bytes_sent)} | Last seen {session.last_seen}"
                )
                if cols[1].button("Terminate", key=f"terminate-{session.id}"):
                    session.active = False
                    session.last_seen = datetime.utcnow()
                    db.commit()
                    st.experimental_rerun()

    with tabs[3]:
        st.subheader("Analytics")
        total_media = len(list_media(db))
        total_sessions = db.query(StreamSession).count()
        total_bytes = db.query(StreamSession).with_entities(StreamSession.bytes_sent).all()
        total_bytes_value = sum(item[0] for item in total_bytes)
        net = psutil.net_io_counters()
        st.metric("Total Media", total_media)
        st.metric("Total Sessions", total_sessions)
        st.metric("Total Bytes Streamed", format_bytes(total_bytes_value))
        st.write(
            f"Network sent: {format_bytes(net.bytes_sent)} | "
            f"Network received: {format_bytes(net.bytes_recv)}"
        )
