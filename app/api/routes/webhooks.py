import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import WEBHOOK_LIMIT, limiter

router = APIRouter()


async def _configured_secret(db: AsyncSession, key: str, env_fallback: str) -> str:
    """Lee un secreto de webhook desde SystemSetting['integrations'] o .env."""
    from app.models.system_setting import SystemSetting

    setting = await db.get(SystemSetting, "integrations")
    value = ""
    if setting and setting.value:
        value = (setting.value.get(key) or "").strip()
    return value or (env_fallback or "").strip()


def _check_secret(provided: str | None, expected: str) -> None:
    """Valida un secreto de webhook. Fail-closed y en tiempo constante.

    Si no hay secreto configurado se rechaza la peticion: un webhook publico
    permite a cualquiera inyectar mensajes con identidad falsificada.
    """
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Webhook secret no configurado",
        )
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid secret")


@router.post("/whatsapp")
@limiter.limit(WEBHOOK_LIMIT)
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive WhatsApp messages from Evolution API.

    Evolution firma el webhook con la apikey de la instancia; sin verificarla
    cualquiera puede falsificar `key.remoteJid` y suplantar a un cliente.
    """
    expected = await _configured_secret(db, "evolution_api_key", settings.evolution_api_key)
    provided = (
        request.headers.get("apikey")
        or request.headers.get("x-api-key")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    _check_secret(provided, expected)

    body = await request.json()
    event = body.get("event")

    # Log del webhook recibido (no levanta si falla)
    from app.services.webhook_monitor import record_webhook
    await record_webhook(db, source="whatsapp", payload=body, event_type=event)

    if event == "messages.upsert":
        messages = body.get("data", [])
        for msg in messages if isinstance(messages, list) else [messages]:
            if msg.get("key", {}).get("fromMe"):
                continue  # Skip own messages

            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(db, msg)

    return {"ok": True}


@router.post("/telegram")
@limiter.limit(WEBHOOK_LIMIT)
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Telegram updates.

    El secreto viaja en la cabecera X-Telegram-Bot-Api-Secret-Token (mecanismo
    oficial de Telegram). Se acepta el query param `secret` solo por
    compatibilidad con webhooks ya registrados, pero deja el secreto en los
    logs del proxy: re-registra el webhook con secret_token para dejar de
    usarlo.
    """
    expected = await _configured_secret(
        db, "telegram_webhook_secret", settings.telegram_webhook_secret
    )
    provided = request.headers.get("x-telegram-bot-api-secret-token") or request.query_params.get(
        "secret"
    )
    _check_secret(provided, expected)

    body = await request.json()

    # Log del webhook TG recibido
    from app.services.webhook_monitor import record_webhook
    tg_event = "callback_query" if "callback_query" in body else (
        "message" if "message" in body else "other"
    )
    await record_webhook(db, source="telegram", payload=body, event_type=tg_event)

    try:
        if "callback_query" in body:
            from app.services.messaging import handle_telegram_callback
            await handle_telegram_callback(db, body["callback_query"])
        elif "message" in body:
            from app.services.messaging import handle_telegram_message
            await handle_telegram_message(db, body["message"])
    except Exception as e:
        # Log but don't raise — always return 200 to Telegram so it doesn't retry
        import traceback
        print(f"[TG-Webhook] Error processing update: {e}")
        traceback.print_exc()

    return {"ok": True}
