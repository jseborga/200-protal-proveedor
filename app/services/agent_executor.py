"""Agent Executor — cerebro que interpreta mensajes y ejecuta acciones.

Recibe un mensaje de texto (Telegram, WhatsApp, etc.), lo pasa al AI
con function calling, ejecuta acciones en la DB, y devuelve respuesta.
"""

import json
import httpx

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_providers import get_provider_info


# ── Tools disponibles para el agente ──────────────────────────

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_productos",
            "description": "Busca productos/insumos en el catalogo por nombre o categoria. Devuelve nombre, precio, unidad, categoria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto de busqueda (ej: 'cemento', 'fierro 12mm')"},
                    "categoria": {"type": "string", "description": "Filtrar por categoria (opcional)"},
                    "limit": {"type": "integer", "description": "Cantidad maxima de resultados (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_proveedores",
            "description": "Busca proveedores registrados por nombre, ciudad o categoria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto de busqueda"},
                    "ciudad": {"type": "string", "description": "Filtrar por ciudad (opcional)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estadisticas",
            "description": "Obtiene estadisticas generales del sistema: total proveedores, productos, cotizaciones, usuarios, regiones.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "precios_por_region",
            "description": "Obtiene precios de un producto en diferentes regiones para comparar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto": {"type": "string", "description": "Nombre del producto a buscar precios"},
                },
                "required": ["producto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ultimas_cotizaciones",
            "description": "Lista las cotizaciones mas recientes recibidas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Cantidad (default 5)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_tarea",
            "description": "Ejecuta una tarea del sistema: 'material_curation' (curar materiales, detectar duplicados) o 'refresh_prices' (recalcular precios).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tarea": {
                        "type": "string",
                        "enum": ["material_curation", "refresh_prices"],
                        "description": "Nombre de la tarea a ejecutar",
                    },
                },
                "required": ["tarea"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tarea_compleja",
            "description": "Delega una tarea compleja a Claude Code Routine (analisis profundo, clasificacion masiva, scraping, reorganizar catalogo, generar reportes). Usa esto cuando la tarea requiere mucho procesamiento o acceso a codigo/archivos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {
                        "type": "string",
                        "description": "Descripcion detallada de la tarea a ejecutar",
                    },
                },
                "required": ["descripcion"],
            },
        },
    },
]

# Anthropic tool format (different from OpenAI)
AGENT_TOOLS_ANTHROPIC = [
    {
        "name": t["function"]["name"],
        "description": t["function"]["description"],
        "input_schema": t["function"]["parameters"],
    }
    for t in AGENT_TOOLS
]


SYSTEM_PROMPT = """Eres el asistente AI de APU Marketplace, un portal de precios de materiales de construccion en Bolivia.

Tu trabajo es ayudar al administrador respondiendo preguntas y ejecutando acciones sobre el sistema.

Reglas:
- Responde siempre en espanol, breve y directo
- Usa las herramientas disponibles para consultar datos reales, no inventes
- Si no puedes hacer algo, dilo claramente
- Formatea numeros con 2 decimales y moneda Bs (bolivianos)
- Si te piden ejecutar una tarea, confirma el resultado
"""


# ── Executor principal ────────────────────────────────────────

async def execute_agent_message(
    db: AsyncSession,
    message: str,
    ai_config: dict,
    agent_prompt: str | None = None,
) -> str:
    """Procesa un mensaje del usuario, usa AI + tools, devuelve respuesta texto."""

    system = agent_prompt or SYSTEM_PROMPT
    messages = [{"role": "user", "content": message}]

    # Loop de tool calling (max 5 rounds)
    for _ in range(5):
        ai_response = await _call_ai_with_tools(ai_config, system, messages)

        if ai_response is None:
            return "Error conectando con el servicio de IA."

        # Check if AI wants to call tools
        tool_calls = _extract_tool_calls(ai_config, ai_response)

        if not tool_calls:
            # No tools, return final text
            return _extract_text(ai_config, ai_response)

        # Execute each tool and add results
        if ai_config["api_format"] == "anthropic":
            # Anthropic format: assistant message with tool_use blocks
            messages.append({"role": "assistant", "content": ai_response.get("content", [])})
            tool_results = []
            for tc in tool_calls:
                result = await _execute_tool(db, tc["name"], tc["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            # OpenAI format
            messages.append(ai_response.get("message", ai_response))
            for tc in tool_calls:
                result = await _execute_tool(db, tc["name"], tc["input"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

    return _extract_text(ai_config, ai_response)


# ── AI call with tools ────────────────────────────────────────

async def _call_ai_with_tools(config: dict, system: str, messages: list) -> dict | None:
    """Llama al AI con tools habilitados."""
    try:
        if config["api_format"] == "anthropic":
            return await _call_anthropic(config, system, messages)
        else:
            return await _call_openai_compat(config, system, messages)
    except Exception as e:
        print(f"[AgentExecutor] AI call error: {e}")
        return None


async def _call_anthropic(config: dict, system: str, messages: list) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            config["base_url"],
            headers={
                "x-api-key": config["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": config["model"],
                "system": system,
                "messages": messages,
                "tools": AGENT_TOOLS_ANTHROPIC,
                "max_tokens": 2000,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _call_openai_compat(config: dict, system: str, messages: list) -> dict:
    """OpenAI, Google AI Studio, OpenRouter — all OpenAI-compatible."""
    url = config["base_url"].rstrip("/")
    if config["api_format"] == "openrouter":
        endpoint = url
    else:
        endpoint = f"{url}/chat/completions" if not url.endswith("/chat/completions") else url

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    if config["api_format"] == "openrouter":
        headers["HTTP-Referer"] = "https://apu-marketplace.com"

    full_messages = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m, dict) and "role" in m:
            full_messages.append(m)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            endpoint,
            headers=headers,
            json={
                "model": config["model"],
                "messages": full_messages,
                "tools": AGENT_TOOLS,
                "max_tokens": 2000,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0]


# ── Parse AI responses ────────────────────────────────────────

def _extract_tool_calls(config: dict, response: dict) -> list[dict]:
    """Extrae tool calls de la respuesta AI (formato normalizado)."""
    calls = []

    if config["api_format"] == "anthropic":
        for block in response.get("content", []):
            if block.get("type") == "tool_use":
                calls.append({
                    "id": block["id"],
                    "name": block["name"],
                    "input": block.get("input", {}),
                })
    else:
        msg = response.get("message", response)
        for tc in msg.get("tool_calls", []):
            args = tc.get("function", {}).get("arguments", "{}")
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = {}
            calls.append({
                "id": tc["id"],
                "name": tc["function"]["name"],
                "input": parsed,
            })

    return calls


def _extract_text(config: dict, response: dict) -> str:
    """Extrae texto final de la respuesta AI."""
    if config["api_format"] == "anthropic":
        for block in response.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return ""
    else:
        msg = response.get("message", response)
        return msg.get("content", "") or ""


# ── Tool implementations ──────────────────────────────────────

async def _execute_tool(db: AsyncSession, name: str, args: dict) -> dict:
    """Ejecuta una herramienta y devuelve el resultado."""
    try:
        if name == "buscar_productos":
            return await _tool_buscar_productos(db, **args)
        elif name == "buscar_proveedores":
            return await _tool_buscar_proveedores(db, **args)
        elif name == "estadisticas":
            return await _tool_estadisticas(db)
        elif name == "precios_por_region":
            return await _tool_precios_region(db, **args)
        elif name == "ultimas_cotizaciones":
            return await _tool_ultimas_cotizaciones(db, **args)
        elif name == "ejecutar_tarea":
            return await _tool_ejecutar_tarea(db, **args)
        elif name == "tarea_compleja":
            return await _tool_tarea_compleja(db, **args)
        else:
            return {"error": f"Herramienta no encontrada: {name}"}
    except Exception as e:
        return {"error": str(e)[:200]}


async def _tool_buscar_productos(db: AsyncSession, query: str, categoria: str = "", limit: int = 10) -> dict:
    from app.models.insumo import Insumo

    q = select(Insumo).where(
        Insumo.name.ilike(f"%{query}%")
    ).limit(min(limit, 20))

    if categoria:
        q = q.where(Insumo.category.ilike(f"%{categoria}%"))

    result = await db.execute(q)
    items = result.scalars().all()

    return {
        "total": len(items),
        "productos": [
            {
                "nombre": i.name,
                "categoria": i.category,
                "unidad": i.uom,
                "precio_ref": i.ref_price,
                "region": i.region,
            }
            for i in items
        ],
    }


async def _tool_buscar_proveedores(db: AsyncSession, query: str, ciudad: str = "") -> dict:
    from app.models.supplier import Supplier

    q = select(Supplier).where(
        Supplier.name.ilike(f"%{query}%")
    ).limit(10)

    if ciudad:
        q = q.where(Supplier.city.ilike(f"%{ciudad}%"))

    result = await db.execute(q)
    items = result.scalars().all()

    return {
        "total": len(items),
        "proveedores": [
            {
                "nombre": s.name,
                "ciudad": s.city,
                "telefono": s.phone,
                "whatsapp": s.whatsapp,
                "email": s.email,
                "categorias": s.categories or [],
            }
            for s in items
        ],
    }


async def _tool_estadisticas(db: AsyncSession) -> dict:
    from app.models.supplier import Supplier
    from app.models.insumo import Insumo
    from app.models.quotation import Quotation
    from app.models.user import User

    suppliers = (await db.execute(select(func.count(Supplier.id)))).scalar() or 0
    products = (await db.execute(select(func.count(Insumo.id)))).scalar() or 0
    quotations = (await db.execute(select(func.count(Quotation.id)))).scalar() or 0
    users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    regions = (await db.execute(select(func.count(func.distinct(Insumo.region))))).scalar() or 0

    return {
        "proveedores": suppliers,
        "productos": products,
        "cotizaciones": quotations,
        "usuarios": users,
        "regiones": regions,
    }


async def _tool_precios_region(db: AsyncSession, producto: str) -> dict:
    from app.models.insumo import Insumo

    result = await db.execute(
        select(Insumo.name, Insumo.region, Insumo.ref_price, Insumo.uom)
        .where(Insumo.name.ilike(f"%{producto}%"))
        .where(Insumo.ref_price.isnot(None))
        .order_by(Insumo.ref_price)
        .limit(20)
    )
    rows = result.all()

    return {
        "producto": producto,
        "precios": [
            {"nombre": r[0], "region": r[1], "precio": r[2], "unidad": r[3]}
            for r in rows
        ],
    }


async def _tool_ultimas_cotizaciones(db: AsyncSession, limit: int = 5) -> dict:
    from app.models.quotation import Quotation

    result = await db.execute(
        select(Quotation)
        .order_by(Quotation.created_at.desc())
        .limit(min(limit, 10))
    )
    items = result.scalars().all()

    return {
        "total": len(items),
        "cotizaciones": [
            {
                "id": q.id,
                "proveedor": q.supplier_name,
                "archivo": q.original_filename,
                "lineas": q.line_count,
                "estado": q.state,
                "fecha": q.created_at.isoformat() if q.created_at else None,
            }
            for q in items
        ],
    }


async def _tool_ejecutar_tarea(db: AsyncSession, tarea: str) -> dict:
    if tarea == "material_curation":
        try:
            from app.tasks.material_curation import run_material_curation
            result = await run_material_curation()
            return {"tarea": "material_curation", "estado": "completada", "resultado": result}
        except Exception as e:
            return {"tarea": "material_curation", "estado": "error", "error": str(e)[:200]}
    elif tarea == "refresh_prices":
        try:
            from app.tasks.price_refresh import run_price_refresh
            result = await run_price_refresh()
            return {"tarea": "refresh_prices", "estado": "completada", "resultado": result}
        except Exception as e:
            return {"tarea": "refresh_prices", "estado": "error", "error": str(e)[:200]}
    else:
        return {"error": f"Tarea no reconocida: {tarea}"}


# ── Resolve config for agent ──────────────────────────────────

async def resolve_agent_config(db: AsyncSession, agent_type: str | None = None) -> dict | None:
    """Resuelve la config AI para un agente: agente especifico → global → .env."""
    from app.models.system_setting import SystemSetting
    from app.models.ai_agent import AIAgent
    from app.core.config import settings

    # 1. Buscar agente activo del tipo pedido
    agent_prompt = None
    if agent_type:
        result = await db.execute(
            select(AIAgent)
            .where(AIAgent.agent_type == agent_type, AIAgent.is_active == True)
            .limit(1)
        )
        agent = result.scalar_one_or_none()
        if agent:
            agent_prompt = agent.system_prompt
            if agent.provider and agent.api_key:
                provider = get_provider_info(agent.provider)
                if provider:
                    config = {
                        "provider": agent.provider,
                        "api_key": agent.api_key,
                        "model": agent.model or provider["default_model"],
                        "base_url": provider["base_url"],
                        "api_format": provider["api_format"],
                    }
                    return config, agent_prompt

    # 2. Global system config
    setting = await db.get(SystemSetting, "ai_config")
    if setting and setting.value and setting.value.get("api_key"):
        from app.services.ai_extract import _build_config
        config = _build_config(setting.value)
        return config, agent_prompt

    # 3. Fallback .env
    if settings.ai_api_key:
        from app.services.ai_extract import _build_config
        config = _build_config({
            "provider": settings.ai_provider,
            "api_key": settings.ai_api_key,
            "model": settings.ai_model,
        })
        return config, agent_prompt

    return None, agent_prompt


# ── Claude Code Routine (tareas complejas) ────────────────────

async def _tool_tarea_compleja(db: AsyncSession, descripcion: str) -> dict:
    """Delega una tarea compleja a Claude Code Routine."""
    result = await fire_routine(db, descripcion)
    return result


async def fire_routine(db: AsyncSession, task_text: str) -> dict:
    """Dispara una Claude Code Routine via API.

    La config (routine_id + bearer token) se lee de SystemSetting 'routine_config'.
    """
    from app.models.system_setting import SystemSetting

    setting = await db.get(SystemSetting, "routine_config")
    if not setting or not setting.value:
        return {"error": "Routine no configurada. Configura routine_id y token en Admin > Integraciones."}

    cfg = setting.value
    routine_id = cfg.get("routine_id", "")
    token = cfg.get("token", "")

    if not routine_id or not token:
        return {"error": "Falta routine_id o token en la configuracion."}

    url = f"https://api.anthropic.com/v1/claude_code/routines/{routine_id}/fire"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "anthropic-beta": "experimental-cc-routine-2026-04-01",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={"text": task_text},
            )

        if resp.status_code == 200:
            data = resp.json()
            session_url = data.get("claude_code_session_url", "")
            session_id = data.get("claude_code_session_id", "")
            return {
                "estado": "iniciada",
                "mensaje": f"Tarea delegada a Claude Code. Session: {session_id}",
                "url": session_url,
            }
        else:
            return {
                "estado": "error",
                "codigo": resp.status_code,
                "error": resp.text[:300],
            }
    except Exception as e:
        return {"estado": "error", "error": str(e)[:300]}
