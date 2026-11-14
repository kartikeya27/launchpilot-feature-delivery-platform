#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v python3 >/dev/null || { echo "Python 3 required"; exit 1; }
command -v node >/dev/null || { echo "Node.js required (Node 22.12+ recommended)"; exit 1; }
command -v npm >/dev/null || { echo "npm required"; exit 1; }
if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "==> Creating virtual environment"
  python3 -m venv "$ROOT/backend/.venv"
fi
"$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements-dev.txt"
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "==> Installing frontend packages"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund)
fi
cleanup() { if [ -n "${API_PID:-}" ]; then kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; fi; }
trap cleanup EXIT INT TERM
echo "==> Launching API on http://127.0.0.1:8000"
(cd "$ROOT/backend" && "$ROOT/backend/.venv/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
API_PID=$!
echo "==> Launching dashboard on http://127.0.0.1:5173"
(cd "$ROOT/frontend" && npm run dev)
