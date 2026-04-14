FROM python:3.12-slim AS base

WORKDIR /app

# System deps for asyncpg + bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir . && pip install email-validator

# App code
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["bash", "scripts/start.sh"]
