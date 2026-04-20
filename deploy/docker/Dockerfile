# StankBot — container image.
# Non-root, uv-based install, SQLite data lives in /data (bind-mount a host dir).

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 stankbot

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip && pip install .

RUN install -d -o stankbot -g stankbot /data
USER stankbot

ENV DATABASE_URL=sqlite+aiosqlite:////data/stankbot.db

EXPOSE 8000

CMD ["python", "-m", "stankbot"]
