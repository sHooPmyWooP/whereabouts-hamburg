#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
uv_command="${UV_COMMAND:-uv}"

if ! command -v "$uv_command" >/dev/null 2>&1; then
  uv_command="$HOME/.local/bin/uv"
fi

# Find the next free TCP port at or above the given base.
find_free_port() {
  local port="$1"
  while :; do
    if ! { exec 3<>"/dev/tcp/127.0.0.1/$port"; } 2>/dev/null; then
      echo "$port"
      return 0
    fi
    exec 3>&- 3<&- 2>/dev/null || true
    port=$((port + 1))
  done
}

backend_port="$(find_free_port "${BACKEND_PORT:-8000}")"
frontend_port="$(find_free_port "${FRONTEND_PORT:-5173}")"

frontend_origin="http://localhost:${frontend_port}"
api_base_url="http://localhost:${backend_port}"

echo "Backend:  ${api_base_url}"
echo "Frontend: ${frontend_origin}"

cleanup() {
  kill "${backend_pid:-}" "${frontend_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Seed .env files from the examples on first run.
for dir in backend frontend; do
  if [ ! -f "$root_dir/$dir/.env" ] && [ -f "$root_dir/$dir/.env.example" ]; then
    cp "$root_dir/$dir/.env.example" "$root_dir/$dir/.env"
    echo "Created $dir/.env from .env.example"
  fi
done

# Install frontend deps if missing (vite lives in node_modules).
if [ ! -x "$root_dir/frontend/node_modules/.bin/vite" ]; then
  (cd "$root_dir/frontend" && npm install)
fi

(cd "$root_dir/backend" && FRONTEND_ORIGIN="$frontend_origin" \
  "$uv_command" run uvicorn main:app --reload --host 0.0.0.0 --port "$backend_port") &
backend_pid=$!

(cd "$root_dir/frontend" && VITE_API_BASE_URL="$api_base_url" \
  npm run dev -- --host 0.0.0.0 --port "$frontend_port" --strictPort) &
frontend_pid=$!

wait "$backend_pid" "$frontend_pid"
