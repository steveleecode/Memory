#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${MEMORY_API_PORT:-8000}"
WEB_PORT="${MEMORY_WEB_PORT:-5173}"
COMPOSE_FILE="$ROOT_DIR/infrastructure/docker-compose.yml"
API_ENV_FILE="$ROOT_DIR/apps/api/.env"

api_pid=""
web_pid=""

cleanup() {
  if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null; then
    kill "$api_pid" 2>/dev/null || true
  fi

  if [[ -n "$web_pid" ]] && kill -0 "$web_pid" 2>/dev/null; then
    kill "$web_pid" 2>/dev/null || true
  fi
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"

  for _ in {1..40}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label is ready: $url"
      return 0
    fi
    sleep 0.5
  done

  echo "$label did not become ready at $url" >&2
  return 1
}

trap cleanup EXIT INT TERM

require_command docker
require_command pnpm
require_command curl

if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
  echo "Python dependencies are not installed. Run:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/pip install -e 'apps/api[dev]'" >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/node_modules" ]]; then
  echo "JavaScript dependencies are not installed. Run:" >&2
  echo "  pnpm install" >&2
  exit 1
fi

if [[ ! -f "$API_ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$API_ENV_FILE"
  echo "Created apps/api/.env from .env.example"
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then run this script again." >&2
  exit 1
fi

echo "Starting local services..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Applying database migrations..."
(
  cd "$ROOT_DIR/apps/api"
  ../../.venv/bin/alembic upgrade head
)

echo "Starting Memory API on http://127.0.0.1:$API_PORT"
"$ROOT_DIR/.venv/bin/uvicorn" app.main:app \
  --app-dir "$ROOT_DIR/apps/api" \
  --host 127.0.0.1 \
  --port "$API_PORT" \
  --reload &
api_pid="$!"

wait_for_http "http://127.0.0.1:$API_PORT/health" "Memory API"

echo "Starting Memory web app on http://127.0.0.1:$WEB_PORT"
if [[ "$WEB_PORT" != "5173" ]]; then
  pnpm --dir "$ROOT_DIR/apps/web" vite --host 127.0.0.1 --port "$WEB_PORT" &
else
  pnpm --dir "$ROOT_DIR/apps/web" dev &
fi
web_pid="$!"

echo
echo "Memory is running:"
echo "  Web: http://127.0.0.1:$WEB_PORT"
echo "  API: http://127.0.0.1:$API_PORT"
echo
echo "Press Ctrl+C to stop the API and web dev servers."

wait "$api_pid" "$web_pid"
