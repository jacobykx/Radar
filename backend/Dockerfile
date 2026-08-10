# syntax=docker/dockerfile:1

# ── builder ────────────────────────────────────────────────────────────────────
# Poetry exports a locked requirements set and installs it into a virtualenv that the
# runtime stage copies wholesale. Poetry itself never reaches the final image.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.3.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install "poetry==${POETRY_VERSION}"

# Dependency layer first: it only rebuilds when the lockfile changes, not on every
# source edit.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY app ./app
COPY scripts ./scripts
COPY alembic.ini ./
RUN poetry install --only main

# ── runtime ────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as an unprivileged user; nothing in this service needs root.
RUN useradd --create-home --uid 10001 iap

WORKDIR /app

COPY --from=builder --chown=iap:iap /app/.venv ./.venv
COPY --chown=iap:iap app ./app
COPY --chown=iap:iap scripts ./scripts
COPY --chown=iap:iap alembic.ini ./

USER iap

EXPOSE 8010

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=2).status == 200 else 1)"

# Migrations are NOT run here. Schema changes are a deploy step with its own approval,
# not a side effect of a container starting -- see `migrate` in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
