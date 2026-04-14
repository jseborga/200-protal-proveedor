FROM python:3.12-slim

WORKDIR /app

# System dependencies: compiladores para asyncpg/bcrypt, libpq para PostgreSQL, curl para healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer — solo se reconstruye si cambia requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code + frontend + migrations + scripts
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini .
COPY pyproject.toml .

# Permisos para el script de inicio
RUN chmod +x scripts/start.sh

# Usuario no-root para seguridad
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["bash", "scripts/start.sh"]
