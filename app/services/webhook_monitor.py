"""Registro y consulta del historial de webhooks entrantes.

Funciones principales:
- record_webhook(): guarda un row en mkt_webhook_log y rota (elimina los
  m\u00e1s viejos manteniendo \u00faltimos N por source).
- last_webhook_by_instance(): devuelve {instance_name: {received_at, event_type}}
  para la UI de salud.
- evolution_connection_state(): consulta /instance/connectionState/{instance}
  de Evolution para cada instancia configurada.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_log import WebhookLog

# Mantener solo los \u00faltimos N webhooks por source. Rotaci\u00f3n suave: se ejecuta
# aproximadamente cada RETENTION_PRUNE_EVERY inserts para no pagar el DELETE
# en cada webhook.
WEBHOOK_LOG_RETENTION = 1000
RETENTION_PRUNE_EVERY = 50


def _extract_instance_name(payload: dict, source: str) -> str | None:
    """Intenta identificar la instancia desde el payload Evolution/Telegram."""
    if not isinstance(payload, dict):
        return None
    if source == "whatsapp":
        # Evolution v2 manda "instance" o "instanceName" en el payload
        return (
            payload.get("instance")
            or payload.get("instanceName")
            or payload.get("instance_name")
        )
    return None


async def record_webhook(
    db: AsyncSession,
    *,
    source: str,
    payload: dict[str, Any],
    status: str = "received",
    error: str | None = None,
    event_type: str | None = None,
    instance_name: str | None = None,
) -> WebhookLog:
    """Registra un evento de webhook. No levanta excepciones: el caller
    no debe fallar si el log falla."""
    try:
        ev = event_type or (payload.get("event") if isinstance(payload, dict) else None)
        inst = instance_name or _extract_instance_name(payload, source)
        row = WebhookLog(
            source=source,
            event_type=ev,
            instance_name=inst,
            status=status,
            payload=payload if isinstance(payload, dict) else {"raw": str(payload)[:500]},
            error=error,
        )
        db.add(row)
        await db.flush()
        # Rotaci\u00f3n ~ cada RETENTION_PRUNE_EVERY
        if row.id and row.id % RETENTION_PRUNE_EVERY == 0:
            await _prune_old(db, source)
        return row
    except Exception as exc:  # pragma: no cover - defensivo
        # Nunca romper el flujo del webhook por un fallo de logging
        print(f"[webhook_monitor] record_webhook failed: {exc}")
        return None  # type: ignore[return-value]


async def _prune_old(db: AsyncSession, source: str) -> int:
    """Borra webhooks m\u00e1s viejos dejando los \u00faltimos WEBHOOK_LOG_RETENTION."""
    # Subquery: ids m\u00e1s viejos a borrar
    keep_ids_stmt = (
        select(WebhookLog.id)
        .where(WebhookLog.source == source)
        .order_by(desc(WebhookLog.id))
        .limit(WEBHOOK_LOG_RETENTION)
    )
    result = await db.execute(keep_ids_stmt)
    keep_ids = [r[0] for r in result.all()]
    if len(keep_ids) < WEBHOOK_LOG_RETENTION:
        return 0  # a\u00fan no hace falta rotar
    stmt = delete(WebhookLog).where(
        WebhookLog.source == source,
        WebhookLog.id.notin_(keep_ids),
    )
    res = await db.execute(stmt)
    return res.rowcount or 0


async def last_webhook_by_instance(
    db: AsyncSession, source: str = "whatsapp",
) -> dict[str, dict[str, Any]]:
    """Devuelve el \u00faltimo webhook por instancia_name.

    Formato: {instance_name: {received_at: ISO, event_type: str, status: str}}
    Si hay webhooks sin instance_name, se agrupan bajo la clave "__unknown__".
    """
    stmt = (
        select(WebhookLog)
        .where(WebhookLog.source == source)
        .order_by(desc(WebhookLog.id))
        .limit(500)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.instance_name or "__unknown__"
        if key in out:
            continue  # ya tenemos el m\u00e1s reciente
        ts = row.received_at
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[key] = {
            "received_at": ts.isoformat() if ts else None,
            "event_type": row.event_type,
            "status": row.status,
        }
    return out


async def evolution_connection_state(
    url: str, instance_name: str, api_key: str, timeout: float = 5.0,
) -> dict[str, Any]:
    """Consulta GET {url}/instance/connectionState/{instance}.

    Devuelve {state, raw, error}. state puede ser: open | close | connecting | unknown.
    Nunca levanta; siempre retorna dict con campo state y opcional error.
    """
    if not url or not instance_name:
        return {"state": "unknown", "error": "missing url/instance"}
    endpoint = f"{url.rstrip('/')}/instance/connectionState/{instance_name}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                endpoint, headers={"apikey": api_key} if api_key else {},
            )
            if resp.status_code >= 400:
                return {
                    "state": "unknown",
                    "error": f"HTTP {resp.status_code}",
                    "raw": resp.text[:300],
                }
            data = resp.json()
            # Evolution v2 devuelve {"instance": {"state": "open", ...}}
            inst = data.get("instance") if isinstance(data, dict) else {}
            state = (inst or {}).get("state") or data.get("state") or "unknown"
            return {"state": state, "raw": data}
    except Exception as exc:
        return {"state": "unknown", "error": str(exc)[:200]}
