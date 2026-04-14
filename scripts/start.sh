#!/bin/bash
set -e

echo "=== APU Marketplace — Starting ==="
echo ">> Env: ${APP_ENV:-production}"

# ── Fase 1: Migraciones Alembic (si existen) ───────────
# Cuando el proyecto crezca y tenga migraciones versionadas,
# Alembic las aplica aqui. Si falla (no hay migraciones aun),
# la app crea las tablas automaticamente en el startup (main.py)
if [ -f "alembic.ini" ] && [ -d "migrations/versions" ] && [ "$(ls -A migrations/versions/ 2>/dev/null)" ]; then
    echo ">> Aplicando migraciones Alembic..."
    python -m alembic upgrade head || echo ">> WARN: Alembic fallo, tablas se crean via app startup"
else
    echo ">> Sin migraciones Alembic, tablas se crean automaticamente al iniciar"
fi

# ── Fase 2: Arrancar uvicorn ───────────────────────────
echo ">> Iniciando uvicorn en puerto ${APP_PORT:-8000}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${APP_PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --log-level "${LOG_LEVEL:-info}"
