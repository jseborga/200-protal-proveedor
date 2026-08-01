"""Resolucion de la IP real del cliente detras de proxies.

Las cabeceras X-Forwarded-For / CF-Connecting-IP / X-Real-IP las envia el
cliente, asi que solo son fiables cuando la conexion TCP proviene de un proxy
que controlamos. Confiar en ellas sin filtro permite (a) saltarse el rate limit
rotando la cabecera y (b) envenenar la banlist haciendo banear la IP de un
tercero.

Configuracion: TRUSTED_PROXIES en .env (lista de CIDRs). Vacio = ignorar
siempre las cabeceras y usar la IP del socket.
"""
import ipaddress
import logging

from .config import settings

logger = logging.getLogger(__name__)

_FORWARD_HEADERS = ("cf-connecting-ip", "x-forwarded-for", "x-real-ip")


def _parse_networks(raw: list[str]) -> list[ipaddress._BaseNetwork]:
    nets = []
    for entry in raw or []:
        entry = (entry or "").strip()
        if not entry:
            continue
        try:
            nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXIES: entrada invalida ignorada: %r", entry)
    return nets


_TRUSTED_NETWORKS = _parse_networks(settings.trusted_proxies)


def _is_trusted_proxy(peer: str | None) -> bool:
    if not peer or not _TRUSTED_NETWORKS:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_NETWORKS)


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def resolve_client_ip(headers: dict[str, str], peer: str | None) -> str:
    """IP del cliente: cabeceras de proxy solo si `peer` es un proxy confiable."""
    if _is_trusted_proxy(peer):
        for header in _FORWARD_HEADERS:
            ip = _valid_ip(headers.get(header))
            if ip:
                return ip
    return peer or "unknown"
