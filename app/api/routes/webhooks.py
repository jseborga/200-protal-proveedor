import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

router = APIRouter()


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive WhatsApp messages from Evolution API."""
    body = await request.json()
    event = body.get("event")

    if event == "messages.upsert":
        messages = body.get("data", [])
        for msg in messages if isinstance(messages, list) else [messages]:
            if msg.get("key", {}).get("fromMe"):
                continue  # Skip own messages

            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(db, msg)

    return {"ok": True}


@router.post("/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Telegram updates."""
    # Verify webhook secret via query param (check DB config first, then .env)
    secret = request.query_params.get("secret")
    from app.models.system_setting import SystemSetting
    tg_setting = await db.get(SystemSetting, "integrations")
    expected_secret = ""
    if tg_setting and tg_setting.value:
        expected_secret = tg_setting.value.get("telegram_webhook_secret", "")
    if not expected_secret:
        expected_secret = settings.telegram_webhook_secret
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()

    if "message" in body:
        try:
            from app.services.messaging import handle_telegram_message
            await handle_telegram_message(db, body["message"])
        except Exception as e:
            # Log but don't raise — always return 200 to Telegram so it doesn't retry
            import traceback
            print(f"[TG-Webhook] Error processing message: {e}")
            traceback.print_exc()

    return {"ok": True}
