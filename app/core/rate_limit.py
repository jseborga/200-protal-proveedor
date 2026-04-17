"""Rate limiting para endpoints publicos (anti-scraping).

Usa slowapi con storage en memoria por defecto. Para produccion multi-worker
configurar RATELIMIT_STORAGE_URI=redis://... en el entorno.

Respeta cabeceras de proxy (X-Forwarded-For / X-Real-IP) cuando el servidor
esta detras de Cloudflare o un reverse proxy.
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _client_key(request: Request) -> str:
    """Obtiene la IP real del cliente respetando cabeceras de proxy."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real
    return get_remote_address(request)


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
