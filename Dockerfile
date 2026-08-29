# syntax=docker/dockerfile:1.7

FROM node:24-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.12-slim AS runtime
ENV APP_ENV=production \
    PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=uv /uv /uvx /bin/
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY data/ /app/data/
COPY --from=frontend-build /build/frontend/dist/ /app/frontend/dist/

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
