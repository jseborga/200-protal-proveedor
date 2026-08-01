"""Rate limiting para endpoints publicos (anti-scraping).

Usa slowapi con storage en memoria por defecto. Para produccion multi-worker
configurar RATELIMIT_STORAGE_URI=redis://... en el entorno.

Respeta cabeceras de proxy (X-Forwarded-For / X-Real-IP) SOLO cuando la
conexion llega desde un proxy declarado en TRUSTED_PROXIES; de lo contrario
cualquier cliente podria rotar la cabecera para saltarse el limite.
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .client_ip import resolve_client_ip


def _client_key(request: Request) -> str:
    """Obtiene la IP real del cliente respetando solo proxies confiables."""
    peer = request.client.host if request.client else None
    ip = resolve_client_ip(dict(request.headers), peer)
    return ip if ip != "unknown" else get_remote_address(request)


limiter = Limiter(
    key_func=_client_key,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    headers_enabled=False,  # slowapi requiere response: Response en la firma
    # del endpoint para inyectar los headers; lo desactivamos para no
    # tener que anadir el parametro a cada endpoint decorado.
)

# Limites por tipo de endpoint (override via env si se requiere)
PUBLIC_LIMIT = os.getenv("RATELIMIT_PUBLIC", "60/minute")
SEARCH_LIMIT = os.getenv("RATELIMIT_SEARCH", "30/minute")
AUTH_LIMIT = os.getenv("RATELIMIT_AUTH", "10/minute")
WEBHOOK_LIMIT = os.getenv("RATELIMIT_WEBHOOK", "120/minute")
