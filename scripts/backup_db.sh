#!/usr/bin/env bash
#
# Respaldo de la base de datos con verificacion de restauracion.
#
# El punto clave: NO basta con generar el dump. Un respaldo que nunca se
# restauro es una suposicion, no un respaldo. Este script restaura cada copia
# en una base descartable y comprueba que las tablas criticas tengan filas
# antes de darla por buena.
#
# Uso:
#   ./scripts/backup_db.sh                 respalda y verifica
#   ./scripts/backup_db.sh --no-verify     solo respalda (mas rapido)
#
# Variables (o .env del proyecto):
#   DATABASE_URL      postgres://usuario:clave@host:puerto/base
#   BACKUP_DIR        destino (default ./backups)
#   BACKUP_KEEP_DAYS  retencion en dias (default 30)
#
# Cron sugerido (3:15 AM):
#   15 3 * * * cd /ruta/al/proyecto && ./scripts/backup_db.sh >> backups/backup.log 2>&1

set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$RAIZ/backups}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
VERIFICAR=1
[[ "${1:-}" == "--no-verify" ]] && VERIFICAR=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fallo() { log "ERROR: $*" >&2; exit 1; }

# Cualquier error imprime la linea culpable en vez de morir en silencio.
trap 'fallo "fallo en la linea $LINENO"' ERR

# ── Configuracion ──────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" && -f "$RAIZ/.env" ]]; then
    # Solo se toma DATABASE_URL; no se evalua el .env entero.
    DATABASE_URL="$(grep -E '^DATABASE_URL=' "$RAIZ/.env" | head -1 | cut -d= -f2- || true)"
    DATABASE_URL="${DATABASE_URL%\"}"; DATABASE_URL="${DATABASE_URL#\"}"
fi
[[ -n "${DATABASE_URL:-}" ]] || fallo "Falta DATABASE_URL (en el entorno o en .env)"

# SQLAlchemy usa postgresql+asyncpg://; las herramientas de Postgres no.
URL_PG="${DATABASE_URL/+asyncpg/}"
URL_PG="${URL_PG/postgresql+psycopg2/postgresql}"

command -v pg_dump >/dev/null || fallo "pg_dump no esta instalado"
command -v psql >/dev/null || fallo "psql no esta instalado"

mkdir -p "$BACKUP_DIR"
SELLO="$(date '+%Y%m%d_%H%M%S')"
ARCHIVO="$BACKUP_DIR/apu_${SELLO}.dump"

# ── Respaldo ───────────────────────────────────────────────────
# Formato custom (-Fc): comprimido y restaurable selectivamente con pg_restore.
log "Respaldando a $(basename "$ARCHIVO")"
pg_dump --dbname="$URL_PG" --format=custom --no-owner --no-privileges \
        --file="$ARCHIVO"

[[ -s "$ARCHIVO" ]] || fallo "el respaldo salio vacio"
TAMANO="$(du -h "$ARCHIVO" | cut -f1)"
log "Respaldo generado ($TAMANO)"

# El listado del dump prueba que el archivo no esta corrupto.
pg_restore --list "$ARCHIVO" >/dev/null || fallo "el respaldo esta corrupto"

# ── Verificacion por restauracion real ─────────────────────────
if [[ "$VERIFICAR" -eq 1 ]]; then
    BASE_PRUEBA="verif_respaldo_${SELLO}"
    URL_ADMIN="${URL_PG%/*}/postgres"
    log "Verificando: restaurando en la base descartable $BASE_PRUEBA"

    # Pase lo que pase, la base de prueba se elimina.
    limpiar() {
        psql --dbname="$URL_ADMIN" -q -c \
            "DROP DATABASE IF EXISTS \"$BASE_PRUEBA\";" >/dev/null 2>&1 || true
    }
    trap 'limpiar; fallo "fallo en la linea $LINENO"' ERR
    trap limpiar EXIT

    psql --dbname="$URL_ADMIN" -q -c "CREATE DATABASE \"$BASE_PRUEBA\";"
    URL_PRUEBA="${URL_PG%/*}/$BASE_PRUEBA"

    # --exit-on-error para que un fallo de restauracion no pase inadvertido.
    pg_restore --dbname="$URL_PRUEBA" --no-owner --no-privileges \
               --exit-on-error "$ARCHIVO" >/dev/null

    # Que las tablas existan no alcanza: tienen que traer datos.
    for tabla in mkt_insumo mkt_user mkt_company; do
        FILAS="$(psql --dbname="$URL_PRUEBA" -tAc "SELECT count(*) FROM $tabla;" 2>/dev/null || echo 0)"
        [[ "$FILAS" -gt 0 ]] || fallo "verificacion fallida: $tabla quedo vacia tras restaurar"
        log "  $tabla: $FILAS filas"
    done

    log "Verificacion OK: el respaldo se restaura y trae datos"
fi

# ── Retencion ──────────────────────────────────────────────────
BORRADOS="$(find "$BACKUP_DIR" -name 'apu_*.dump' -type f -mtime "+$BACKUP_KEEP_DAYS" -print -delete | wc -l)"
[[ "$BORRADOS" -gt 0 ]] && log "Eliminados $BORRADOS respaldos con mas de $BACKUP_KEEP_DAYS dias"

TOTAL="$(find "$BACKUP_DIR" -name 'apu_*.dump' -type f | wc -l)"
log "Listo. $TOTAL respaldos en $BACKUP_DIR"

# Recordatorio deliberado: un respaldo en el mismo disco que la base no
# protege contra la perdida del disco.
if [[ -z "${BACKUP_REMOTE_OK:-}" ]]; then
    log "AVISO: copia estos respaldos fuera del servidor (S3, otro host, etc.)."
    log "       Un respaldo en el mismo disco que la base no protege de nada."
fi
