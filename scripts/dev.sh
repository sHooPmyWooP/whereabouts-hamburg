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

# Generate a local signing secret when the seeded backend environment still
# contains the deliberately invalid example value.
if grep -q '^SESSION_SECRET=replace-this' "$root_dir/backend/.env"; then
  session_secret="$(
    cd "$root_dir/backend"
    "$uv_command" run python -c 'import secrets; print(secrets.token_urlsafe(48))'
  )"
  sed -i "s|^SESSION_SECRET=.*$|SESSION_SECRET=$session_secret|" \
    "$root_dir/backend/.env"
  echo "Generated SESSION_SECRET in backend/.env"
fi

configured_database_url="${DATABASE_URL:-$(
  sed -n 's/^DATABASE_URL=//p' "$root_dir/backend/.env" | tail -n 1
)}"
# Existing local .env files predate DATABASE_URL in some checkouts. Fall back
# to the shipped development configuration instead of failing during migrations.
if [ -z "$configured_database_url" ]; then
  configured_database_url="$(
    sed -n 's/^DATABASE_URL=//p' "$root_dir/backend/.env.example" | tail -n 1
  )"
fi
if [ -z "$configured_database_url" ]; then
  echo "DATABASE_URL is required in backend/.env." >&2
  exit 1
fi

# The example URL uses the dev-container service name. When running directly
# on the host, provide an isolated PostgreSQL container on a localhost port.
if [[ "$configured_database_url" == *"@postgres:"* ]] && ! (
  cd "$root_dir/backend"
  "$uv_command" run python -c \
    "import socket; socket.gethostbyname('postgres')" >/dev/null 2>&1
); then
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is required for the local development database." >&2
    echo "Alternatively, set DATABASE_URL in backend/.env to an accessible PostgreSQL instance." >&2
    exit 1
  fi

  dev_database_port="${DEV_DATABASE_PORT:-55432}"
  docker compose -f "$root_dir/compose.dev.yaml" up -d --wait postgres
  configured_database_url="postgresql+psycopg://postgres:postgres@127.0.0.1:${dev_database_port}/whereabouts_hamburg"
  echo "Database: postgresql://127.0.0.1:${dev_database_port}/whereabouts_hamburg"
fi
export DATABASE_URL="$configured_database_url"

# Keep the development schema current before accepting API requests.
(cd "$root_dir/backend" && "$uv_command" run alembic upgrade head)

# Install frontend deps if missing (vite lives in node_modules).
if [ ! -x "$root_dir/frontend/node_modules/.bin/vite" ]; then
  (cd "$root_dir/frontend" && npm install)
fi

(cd "$root_dir/backend" && FRONTEND_ORIGIN="$frontend_origin" \
  "$uv_command" run uvicorn main:app --reload --host 0.0.0.0 --port "$backend_port") &
backend_pid=$!

# Proxy browser API calls through Vite. An empty explicit value overrides a
# possibly stale frontend/.env URL and keeps the browser requests same-origin.
(cd "$root_dir/frontend" && VITE_API_BASE_URL='' VITE_BACKEND_PORT="$backend_port" \
  npm run dev -- --host 0.0.0.0 --port "$frontend_port" --strictPort) &
frontend_pid=$!

wait "$backend_pid" "$frontend_pid"
