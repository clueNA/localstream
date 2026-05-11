#!/usr/bin/env bash
set -euo pipefail

uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-8000}" &
uvicorn_pid=$!

streamlit run backend/admin_app.py --server.address 0.0.0.0 --server.port "${STREAMLIT_PORT:-8501}" --server.headless true &
streamlit_pid=$!

trap 'kill ${uvicorn_pid} ${streamlit_pid}' EXIT
wait -n ${uvicorn_pid} ${streamlit_pid}
