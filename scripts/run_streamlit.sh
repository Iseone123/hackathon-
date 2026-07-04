#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="backend/.venv"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -r streamlit/requirements.txt
echo "Streamlit UI → http://0.0.0.0:18493 (API: ${API_URL:-http://127.0.0.1:8000})"
exec "$VENV/bin/streamlit" run streamlit/app.py --server.port 18493 --server.address 0.0.0.0
