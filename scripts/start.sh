#!/bin/bash
set -e

echo "=== APU Marketplace — Starting ==="

# Run migrations (create tables if first deploy)
echo ">> Running database migrations..."
python -m alembic upgrade head 2>/dev/null || echo ">> No migrations to run (tables will be auto-created in dev mode)"

# Start server
echo ">> Starting uvicorn on port ${APP_PORT:-8000}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${APP_PORT:-8000} \
    --workers ${WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}
