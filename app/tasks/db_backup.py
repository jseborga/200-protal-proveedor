"""Respaldo automatico de la base de datos.

Corre dentro del contenedor de la app usando `pg_dump` (lo aporta el paquete
postgresql-client del Dockerfile). Se registra como job del scheduler para
que se vea y se dispare desde el panel de admin como cualquier otra tarea.

Dos cuidados que no son obvios:

1. La contrasena NO se pasa en la linea de comandos: `pg_dump "postgres://
   user:clave@host/db"` deja la clave visible en `ps aux` para cualquiera con
   acceso al contenedor. Se pasa por PGPASSWORD en el entorno del subproceso.
2. Se verifica el dump leyendo su indice con `pg_restore --list`. Un archivo
   truncado o corrupto se detecta ahora y no el dia que haga falta restaurar.

Limitacion deliberada: esto deja el respaldo en el disco del contenedor. Si
el volumen se pierde, se pierden base y respaldos juntos. Configura
BACKUP_DIR sobre un volumen aparte y sincronizalo fuera del servidor.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/app/backups"))
KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "30"))
TIMEOUT_SEC = int(os.getenv("BACKUP_TIMEOUT_SEC", "900"))


def _partes_conexion() -> dict:
    """Descompone DATABASE_URL en argumentos para pg_dump."""
    url = settings.database_url.replace("+asyncpg", "").replace("+psycopg2", "")
    p = urlparse(url)
    if not p.hostname or not p.path:
        raise RuntimeError("DATABASE_URL no tiene un formato utilizable")
    return {
        "host": p.hostname,
        "port": str(p.port or 5432),
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def _purgar_antiguos() -> int:
    """Elimina respaldos mas viejos que la retencion configurada."""
    if not BACKUP_DIR.exists():
        return 0
    limite = datetime.now(timezone.utc).timestamp() - KEEP_DAYS * 86400
    borrados = 0
    for archivo in BACKUP_DIR.glob("apu_*.dump"):
        try:
            if archivo.stat().st_mtime < limite:
                archivo.unlink()
                borrados += 1
        except OSError:
            continue
    return borrados


def _respaldar() -> dict:
    """Genera y verifica el respaldo. Bloqueante: se corre en un hilo."""
    conn = _partes_conexion()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    sello = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    destino = BACKUP_DIR / f"apu_{sello}.dump"

    # La clave viaja por entorno, no por argv (argv se ve en `ps aux`).
    entorno = {**os.environ, "PGPASSWORD": conn["password"]}

    comando = [
        "pg_dump",
        "--host", conn["host"],
        "--port", conn["port"],
        "--username", conn["user"],
        "--dbname", conn["dbname"],
        "--format", "custom",
        "--no-owner",
        "--no-privileges",
        "--file", str(destino),
    ]

    # Lista de argumentos y sin shell: no hay interpolacion que inyectar.
    proceso = subprocess.run(
        comando, env=entorno, capture_output=True, text=True, timeout=TIMEOUT_SEC,
    )
    if proceso.returncode != 0:
        destino.unlink(missing_ok=True)
        # Solo las ultimas lineas del error: el stderr de pg_dump puede ser
        # largo y no debe arrastrar la cadena de conexion al log.
        detalle = (proceso.stderr or "").strip().splitlines()[-3:]
        raise RuntimeError(f"pg_dump fallo: {' | '.join(detalle)[:300]}")

    tamano = destino.stat().st_size
    if tamano == 0:
        destino.unlink(missing_ok=True)
        raise RuntimeError("el respaldo salio vacio")

    # Leer el indice prueba que el archivo es un dump valido y completo.
    verificacion = subprocess.run(
        ["pg_restore", "--list", str(destino)],
        capture_output=True, text=True, timeout=120,
    )
    if verificacion.returncode != 0:
        destino.unlink(missing_ok=True)
        raise RuntimeError("el respaldo quedo corrupto (pg_restore --list fallo)")

    objetos = len([
        l for l in verificacion.stdout.splitlines()
        if l and not l.startswith(";")
    ])
    borrados = _purgar_antiguos()
    restantes = len(list(BACKUP_DIR.glob("apu_*.dump")))

    return {
        "file": destino.name,
        "size_bytes": tamano,
        "size_mb": round(tamano / 1024 / 1024, 2),
        "objects": objetos,
        "deleted_old": borrados,
        "total_backups": restantes,
        "dir": str(BACKUP_DIR),
    }


async def run(db: AsyncSession) -> dict:
    """Punto de entrada del scheduler.

    `db` no se usa: el respaldo lo hace pg_dump con su propia conexion. La
    firma se mantiene por compatibilidad con el resto de los jobs.
    """
    # to_thread para no bloquear el loop mientras corre el dump.
    resultado = await asyncio.to_thread(_respaldar)
    return {
        "ok": True,
        "message": (
            f"Respaldo {resultado['file']} ({resultado['size_mb']} MB, "
            f"{resultado['objects']} objetos). "
            f"{resultado['total_backups']} copias en disco."
        ),
        **resultado,
    }
