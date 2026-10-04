#!/usr/bin/env bash
# Run the existing database locally; never migrates or seeds it automatically.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
backend_pid=""
frontend_pid=""
cleanup() {
  if [ -n "$backend_pid" ]; then kill "$backend_pid" 2>/dev/null || true; fi
  if [ -n "$frontend_pid" ]; then kill "$frontend_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM
cd "$project_dir"
if [ ! -x backend/venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo 'Install the backend and frontend dependencies first; see README.md.' >&2
  exit 1
fi
if curl --fail --silent --max-time 2 http://127.0.0.1:8000/api/v1/health >/dev/null; then
  echo 'Using the backend already running on port 8000.'
else
  if lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo 'Port 8000 is occupied by an unresponsive service. Stop it before retrying.' >&2
    exit 1
  fi
  (cd backend && exec env ENVIRONMENT=development DATABASE_POOL_MODE=pooled CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) &
  backend_pid=$!
fi
if curl --fail --silent --max-time 2 http://127.0.0.1:5173/ >/dev/null; then
  echo 'Using the frontend already running on port 5173.'
else
  (cd frontend && exec npm run dev -- --host 127.0.0.1 --port 5173 --strictPort) &
  frontend_pid=$!
fi
for attempt in {1..30}; do
  if curl --fail --silent --max-time 1 http://127.0.0.1:8000/api/v1/health >/dev/null && curl --fail --silent --max-time 1 http://127.0.0.1:5173/ >/dev/null; then
    echo 'CartPilot is ready: http://127.0.0.1:5173/dashboard'
    echo 'Keep this terminal open. Press Ctrl+C to stop services started here.'
    if command -v open >/dev/null 2>&1; then open http://127.0.0.1:5173/dashboard; fi
    if [ -n "$backend_pid" ] && [ -n "$frontend_pid" ]; then
      while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do sleep 1; done
    elif [ -n "$backend_pid" ]; then wait "$backend_pid"
    elif [ -n "$frontend_pid" ]; then wait "$frontend_pid"
    fi
    exit 0
  fi
  sleep 1
done
echo 'CartPilot did not start. Check the service errors above.' >&2
exit 1
