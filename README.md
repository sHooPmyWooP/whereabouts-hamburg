# Hamburg Whereabouts

A map game for learning Hamburg's Stadtteile. Play a deterministic daily challenge, create shareable seeded rounds, or train district recall with spaced repetition.

## Features

- Daily challenge with five map pins and a shared guess budget
- Shareable rounds generated from a custom seed
- Interactive Stadtteil explorer and training in both name-to-map and map-to-name directions
- Optional accounts with Argon2 password hashing and persistent progress
- Responsive React and Leaflet interface
- FastAPI backend with PostgreSQL persistence and Alembic migrations
- Production Docker image serving the built frontend and API together

## Stack

- Python 3.12, FastAPI, SQLAlchemy, Alembic, Shapely, pyproj
- React 19, TypeScript, Vite, Leaflet
- PostgreSQL 16
- `uv` and npm lockfiles for reproducible dependencies

## Local development

Install `uv`, npm, Docker Engine, and the Docker Compose plugin, then run:

```bash
make dev
```

On first launch, the command creates the local environment files, generates a session-signing secret, starts PostgreSQL on `127.0.0.1:55432`, and applies all Alembic migrations. Database data persists in the `whereabouts-hamburg-dev_postgres-data` Docker volume between runs. Override the host port with `DEV_DATABASE_PORT` when necessary.

The included VS Code dev container remains supported. Open **Dev Containers: Reopen in Container** and select **Hamburg Whereabouts + PostgreSQL**. Inside that container, `make dev` uses the existing `postgres` service instead of starting another database.

To use another PostgreSQL instance, set its complete `DATABASE_URL` in `backend/.env`. `make dev` only starts the development container when the configured URL uses the dev-container hostname `postgres` and that hostname is unavailable.

The services are available at:

- Frontend: <http://localhost:5173>
- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/health>

The satellite basemap is loaded from Esri, so the browser needs access to `server.arcgisonline.com`.

## Checks

```bash
make test
make lint
make build
```

## Homelab deployment with Docker Compose

The production stack runs the application and PostgreSQL on one Docker host. PostgreSQL is only available on the private Compose network, and its data is stored in the `postgres-data` volume. The application applies Alembic migrations before it starts.

1. Install Docker Engine with the Compose plugin on the server, then clone this repository.
2. Create the deployment environment:

   ```bash
   cp .env.example .env
   openssl rand -hex 32       # POSTGRES_PASSWORD
   openssl rand -base64 48    # SESSION_SECRET
   ```

   Put the generated values in `.env` and keep that file out of version control. The database password must be URL-safe because it is embedded in `DATABASE_URL`; the hex command above guarantees that.
3. Build and start the stack:

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

The application is available at `http://<server>:8000` by default. Set `APP_PORT` in `.env` to use another host port.

For an internet-facing deployment, put an HTTPS reverse proxy such as Caddy, Traefik, or Nginx in front of the application. Keep `SESSION_COOKIE_SECURE=true`. If the proxy runs on the same host, set `APP_BIND_ADDRESS=127.0.0.1` so the application port is not exposed directly on the LAN. For direct HTTP-only LAN access, set `SESSION_COOKIE_SECURE=false`.

### Operations

```bash
# Follow application and database logs
docker compose logs -f

# Pull repository changes, rebuild, migrate, and restart
git pull
docker compose up -d --build

# Back up PostgreSQL
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > whereabouts.dump

# Stop the stack without deleting database data
docker compose down
```

`docker compose down -v` permanently deletes the PostgreSQL volume. Do not run it unless destroying all application data is intentional.

## Documentation

- [Product requirements](docs/PRD.md)
- [Implementation handover](docs/IMPLEMENTATION_HANDOVER.md)
- [Domain language](CONTEXT.md)
- [Server-authoritative guessing decision](docs/adr/0001-server-authoritative-guessing.md)
