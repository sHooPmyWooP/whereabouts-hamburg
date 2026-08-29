# Hamburg Whereabouts

A map game for learning Hamburg's Stadtteile. Play a deterministic daily challenge, create shareable seeded rounds, or train district recall with spaced repetition.

## Features

- Daily challenge with five map pins and a shared guess budget
- Shareable rounds generated from a custom seed
- Interactive Stadtteil training in both name-to-map and map-to-name directions
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

The easiest setup is the included dev container with PostgreSQL. Open the repository in VS Code, run **Dev Containers: Reopen in Container**, and select **Hamburg Whereabouts + PostgreSQL** if prompted.

Alternatively, provide your own PostgreSQL 16 instance.

1. Create the backend environment file:

   ```bash
   cp backend/.env.example backend/.env
   uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Put the generated value in `backend/.env` as `SESSION_SECRET`. Adjust `DATABASE_URL` if PostgreSQL is not available at the example address.

2. Install dependencies and run migrations:

   ```bash
   make install
   cd backend && uv run alembic upgrade head && cd ..
   ```

3. Start the backend and frontend:

   ```bash
   make dev
   ```

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

## Docker

Build and run the production image:

```bash
docker build -t whereabouts-hamburg .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL='postgresql+psycopg://user:password@host:5432/database' \
  -e SESSION_SECRET='replace-with-at-least-32-random-characters' \
  -e SESSION_COOKIE_SECURE=false \
  whereabouts-hamburg
```

Then open <http://localhost:8000>.

## Documentation

- [Product requirements](docs/PRD.md)
- [Implementation handover](docs/IMPLEMENTATION_HANDOVER.md)
- [Domain language](CONTEXT.md)
- [Server-authoritative guessing decision](docs/adr/0001-server-authoritative-guessing.md)
