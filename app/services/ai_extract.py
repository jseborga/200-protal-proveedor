"""Extraccion de datos de cotizacion desde Excel, PDF o foto usando IA.

Soporta multiples proveedores de IA configurables desde admin y por empresa:
- Google AI Studio (gratis)
- OpenRouter (multi-modelo)
- Anthropic (Claude)
- OpenAI (GPT)

Resolucion de config: empresa → sistema (admin) → .env fallback
"""

import base64
import io
import json
import re

import httpx

from app.core.config import settings
from app.core.ai_providers import AI_PROVIDERS, DEFAULT_PROVIDER, get_provider_info


# ── Config resolution ──────────────────────────────────────────

async def resolve_ai_config(company_id: int | None = None) -> dict | None:
    """Resuelve la config de IA a usar: empresa → sistema → .env fallback.

    Returns dict con keys: provider, api_key, model, base_url, api_format
    o None si no hay config disponible.
    """
    from app.core.database import async_session
    from app.models.system_setting import SystemSetting

    # 1. Company config (si tiene company_id)
    if company_id:
        from app.models.company import Company
        async with async_session() as db:
            company = await db.get(Company, company_id)
            if company and company.extra_data:
                ai = company.extra_data.get("ai_config")
                if ai and ai.get("api_key"):
                    return _build_config(ai)

    # 2. System config (admin panel)
    async with async_session() as db:
        setting = await db.get(SystemSetting, "ai_config")
        if setting and setting.value and setting.value.get("api_key"):
            return _build_config(setting.value)

    # 3. Fallback to .env
    if settings.ai_api_key:
        return _build_config({
            "provider": settings.ai_provider,
            "api_key": settings.ai_api_key,
            "model": settings.ai_model,
        })

    return None


def _build_config(raw: dict) -> dict:
    """Normaliza la config raw a un dict consistente con provider info."""
    provider_key = raw.get("provider", DEFAULT_PROVIDER)
    provider = get_provider_info(provider_key) or get_provider_info(DEFAULT_PROVIDER)

    return {
        "provider": provider_key,
        "api_key": raw.get("api_key", ""),
        "model": raw.get("model") or provider["default_model"],
        "base_url": provider["base_url"],
        "api_format": provider["api_format"],
    }


# ── Excel extraction (no AI needed) ────────────────────────────
async def extract_quotation_data(
    content: bytes, filename: str, source: str,
    company_id: int | None = None,
) -> dict | None:
    """Extract quotation lines from uploaded file."""
    if source == "excel":
        return _extract_from_excel(content, filename)
    elif source in ("pdf", "photo"):
        return await _extract_with_ai(content, filename, source, company_id)
    return None


def _extract_from_excel(content: bytes, filename: str) -> dict | None:
    """Parse Excel file looking for price-list columns."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if not ws:
        return None

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return None

    # Detect columns by header heuristics
    header = [str(c).lower().strip() if c else "" for c in rows[0]]
    col_map = _detect_columns(header)

    if "name" not in col_map:
        # Try second row as header
        header = [str(c).lower().strip() if c else "" for c in rows[1]]
        col_map = _detect_columns(header)
        rows = rows[1:]

    if "name" not in col_map:
        return None

    lines = []
    for row in rows[1:]:
        name_val = row[col_map["name"]] if col_map.get("name") is not None else None
        if not name_val or str(name_val).strip() == "":
            continue

        line = {"name": str(name_val).strip()}
        if "code" in col_map and col_map["code"] is not None:
            val = row[col_map["code"]]
            if val:
                line["code"] = str(val).strip()
        if "uom" in col_map and col_map["uom"] is not None:
            val = row[col_map["uom"]]
            if val:
                line["uom"] = str(val).strip()
        if "price" in col_map and col_map["price"] is not None:
            val = row[col_map["price"]]
            try:
                line["price"] = float(val)
            except (TypeError, ValueError):
                line["price"] = 0
        if "brand" in col_map and col_map["brand"] is not None:
            val = row[col_map["brand"]]
            if val:
                line["brand"] = str(val).strip()

        lines.append(line)

    wb.close()
    return {"lines": lines, "metadata": {"source": "excel", "filename": filename, "rows": len(lines)}}


def _detect_columns(header: list[str]) -> dict:
    """Heuristic column detection for price list spreadsheets."""
    col_map = {}
    name_keywords = ["descripcion", "nombre", "producto", "material", "insumo", "item", "detalle", "name"]
    code_keywords = ["codigo", "code", "cod", "ref", "sku"]
    uom_keywords = ["unidad", "uom", "und", "medida", "unit"]
    price_keywords = ["precio", "price", "unitario", "p.u.", "pu", "costo", "valor"]
    brand_keywords = ["marca", "brand", "fabricante"]

    for i, col in enumerate(header):
        if any(kw in col for kw in name_keywords) and "name" not in col_map:
            col_map["name"] = i
        elif any(kw in col for kw in code_keywords) and "code" not in col_map:
            col_map["code"] = i
        elif any(kw in col for kw in uom_keywords) and "uom" not in col_map:
            col_map["uom"] = i
        elif any(kw in col for kw in price_keywords) and "price" not in col_map:
            col_map["price"] = i
        elif any(kw in col for kw in brand_keywords) and "brand" not in col_map:
            col_map["brand"] = i

    return col_map


# ── AI extraction (PDF / Photo) ─────────────────────────────────
EXTRACTION_PROMPT = """Extrae los items de esta cotizacion/lista de precios de construccion.
Devuelve SOLO un JSON array con objetos, cada uno con estos campos:
- name: nombre del producto/material
- code: codigo si existe (null si no)
- uom: unidad de medida (m3, kg, m2, pza, ml, bls, lt, gl, etc.)
- price: precio unitario (numero)
- brand: marca si se menciona (null si no)

Ejemplo de respuesta:
[{"name": "Cemento Portland IP-30", "code": null, "uom": "bls", "price": 58.5, "brand": "Viacha"}]

Si no puedes extraer datos, devuelve [].
No incluyas texto adicional, solo el JSON array."""


async def _extract_with_ai(
    content: bytes, filename: str, source: str,
    company_id: int | None = None,
) -> dict | None:
    """Use AI to extract quotation data from PDF or image."""
    config = await resolve_ai_config(company_id)
    if not config or not config.get("api_key"):
        return None

    api_format = config["api_format"]

    if api_format == "openrouter":
        return await _call_openrouter(content, filename, source, config)
    elif api_format == "anthropic":
        return await _call_anthropic(content, filename, source, config)
    elif api_format == "openai":
        return await _call_openai_compatible(content, filename, source, config)

    return None


async def _call_openrouter(
    content: bytes, filename: str, source: str, config: dict,
) -> dict | None:
    """Call OpenRouter API."""
    b64 = base64.b64encode(content).decode()
    media_type = "application/pdf" if source == "pdf" else "image/jpeg"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{b64}"},
                },
            ],
        }
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            config["base_url"],
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={"model": config["model"], "messages": messages, "max_tokens": 4096},
        )

    if resp.status_code != 200:
        return None

    data = resp.json()
    text_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _parse_ai_response(text_content, filename, source, config)


async def _call_anthropic(
    content: bytes, filename: str, source: str, config: dict,
) -> dict | None:
    """Call Anthropic Messages API directly."""
    b64 = base64.b64encode(content).decode()
    media_type = "application/pdf" if source == "pdf" else "image/jpeg"

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                },
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            config["base_url"],
            headers={
                "x-api-key": config["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={"model": config["model"], "messages": messages, "max_tokens": 4096},
        )

    if resp.status_code != 200:
        return None

    data = resp.json()
    text_content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_content += block.get("text", "")

    return _parse_ai_response(text_content, filename, source, config)


async def _call_openai_compatible(
    content: bytes, filename: str, source: str, config: dict,
) -> dict | None:
    """Call OpenAI-compatible API (OpenAI, Google AI Studio)."""
    b64 = base64.b64encode(content).decode()
    media_type = "application/pdf" if source == "pdf" else "image/jpeg"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{b64}"},
                },
            ],
        }
    ]

    base_url = config["base_url"].rstrip("/")
    endpoint = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={"model": config["model"], "messages": messages, "max_tokens": 4096},
        )

    if resp.status_code != 200:
        return None

    data = resp.json()
    text_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _parse_ai_response(text_content, filename, source, config)


def _parse_ai_response(text: str, filename: str, source: str, config: dict) -> dict | None:
    """Parse AI response text into structured data."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        lines = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                lines = json.loads(match.group())
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(lines, list) or not lines:
        return None

    return {
        "lines": lines,
        "metadata": {
            "source": source,
            "filename": filename,
            "ai_provider": config.get("provider", "unknown"),
            "ai_model": config.get("model", "unknown"),
            "items_extracted": len(lines),
        },
    }
