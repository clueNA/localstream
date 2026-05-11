#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-8000}" &
streamlit run backend/admin_app.py --server.address 0.0.0.0 --server.port "${STREAMLIT_PORT:-8501}" --server.headless true
