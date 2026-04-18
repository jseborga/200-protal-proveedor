"""Servicio de embeddings con soporte multi-provider.

Providers:
  - openai : text-embedding-3-small (1536 dims) - columna embedding_openai
  - gemini : text-embedding-004      (768 dims)  - columna embedding_gemini

Config activa viene de mkt_system_setting (key="embeddings_config") con
cache en memoria. Fallback a .env (settings) cuando no hay config en DB.

Lectura: `get_active_config()` devuelve provider/api_key/model/dims/column.
Escritura: `set_active_config(...)` actualiza la fila y refresca la cache.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import httpx

from app.core.config import settings

# ── Catalogo de providers ─────────────────────────────────────
# Cada modelo declara:
#   dims           : dimensiones del vector devuelto (debe coincidir con la columna)
#   column         : embedding_openai (1536) | embedding_gemini (768)
#   request_dims   : opcional. Si el modelo soporta MRL, lo pedimos en la request
#                    para que el vector devuelto tenga exactamente esa dimension.
PROVIDER_SPECS = {
    "openai": {
        "url": "https://api.openai.com/v1/embeddings",
        "default_model": "text-embedding-3-small",
        "models": {
            "text-embedding-3-small": {"dims": 1536, "column": "embedding_openai"},
            "text-embedding-ada-002":  {"dims": 1536, "column": "embedding_openai"},
        },
    },
    "gemini": {
        "url_base": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "text-embedding-004",
        "models": {
            "text-embedding-004": {"dims": 768, "column": "embedding_gemini"},
        },
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/embeddings",
        "default_model": "openai/text-embedding-3-small",
        "models": {
            "openai/text-embedding-3-small":  {"dims": 1536, "column": "embedding_openai"},
            # gemini-001 es MRL: pedimos 768 dims explicitamente para reusar columna
            "google/gemini-embedding-001":    {"dims": 768,  "column": "embedding_gemini", "request_dims": 768},
        },
    },
}

MAX_BATCH = 100
MAX_RETRIES = 4

SETTING_KEY = "embeddings_config"


class EmbeddingError(Exception):
    pass


# ── Cache de configuracion activa ─────────────────────────────
_active_config: dict | None = None


def _resolve_model_spec(provider: str, model: str) -> dict:
    """Devuelve {dims, column, request_dims?} para el modelo seleccionado."""
    spec = PROVIDER_SPECS[provider]
    models = spec["models"]
    if model not in models:
        raise EmbeddingError(f"Modelo '{model}' no soportado para {provider}. Opciones: {list(models)}")
    return dict(models[model])  # copy


def _default_config() -> dict:
    """Config inicial desde .env. Se usa si no hay fila en DB."""
    prov = (settings.embedding_provider or "openai").lower()
    if prov not in PROVIDER_SPECS:
        prov = "openai"
    spec = PROVIDER_SPECS[prov]
    model = settings.embedding_model or spec["default_model"]
    if model not in spec["models"]:
        model = spec["default_model"]
    ms = _resolve_model_spec(prov, model)
    return {
        "provider": prov,
        "api_key": settings.embedding_api_key or "",
        "model": model,
        "dims": ms["dims"],
        "column": ms["column"],
        "request_dims": ms.get("request_dims"),
    }


async def load_active_config(db) -> dict:
    """Carga config desde DB (o default) y la cachea en memoria."""
    global _active_config
    from app.models.system_setting import SystemSetting
    row = await db.get(SystemSetting, SETTING_KEY)
    if row and row.value and isinstance(row.value, dict) and row.value.get("provider"):
        _active_config = _normalize_config(row.value)
    else:
        _active_config = _default_config()
    return _active_config


def _normalize_config(raw: dict) -> dict:
    prov = (raw.get("provider") or "openai").lower()
    if prov not in PROVIDER_SPECS:
        raise EmbeddingError(f"Provider no soportado: {prov}")
    spec = PROVIDER_SPECS[prov]
    model = raw.get("model") or spec["default_model"]
    if model not in spec["models"]:
        raise EmbeddingError(f"Modelo '{model}' no soportado para {prov}")
    ms = _resolve_model_spec(prov, model)
    return {
        "provider": prov,
        "api_key": raw.get("api_key") or "",
        "model": model,
        "dims": ms["dims"],
        "column": ms["column"],
        "request_dims": ms.get("request_dims"),
    }


def get_active_config() -> dict:
    """Devuelve la config activa cacheada. Si no esta cargada, usa defaults."""
    global _active_config
    if _active_config is None:
        _active_config = _default_config()
    return _active_config


async def set_active_config(db, provider: str, api_key: str, model: str | None = None) -> dict:
    """Actualiza config en DB y refresca cache.

    Valida que el modelo exista para el provider y deriva dims.
    """
    from app.models.system_setting import SystemSetting
    prov = provider.lower()
    if prov not in PROVIDER_SPECS:
        raise EmbeddingError(f"Provider no soportado: {prov}")
    spec = PROVIDER_SPECS[prov]
    m = model or spec["default_model"]
    if m not in spec["models"]:
        raise EmbeddingError(f"Modelo '{m}' no soportado para {prov}. Opciones: {list(spec['models'])}")
    ms = _resolve_model_spec(prov, m)

    payload = {
        "provider": prov,
        "api_key": api_key or "",
        "model": m,
        "dims": ms["dims"],
    }
    row = await db.get(SystemSetting, SETTING_KEY)
    if row:
        row.value = payload
    else:
        row = SystemSetting(key=SETTING_KEY, value=payload)
        db.add(row)
    await db.commit()

    global _active_config, _CACHE
    _active_config = _normalize_config(payload)
    _CACHE.clear()  # queries cacheadas son por-provider implicitamente
    return _active_config


def is_configured() -> bool:
    cfg = get_active_config()
    return bool(cfg.get("api_key"))


# ── API HTTP por provider ─────────────────────────────────────
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embebe una lista de textos usando el provider activo."""
    cfg = get_active_config()
    if not cfg.get("api_key"):
        raise EmbeddingError(f"API key no configurada para provider {cfg['provider']}")
    if not texts:
        return []

    out: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(texts), MAX_BATCH):
            chunk = texts[i:i + MAX_BATCH]
            vecs = await _embed_batch(client, cfg, chunk)
            out.extend(vecs)
    return out


async def _embed_batch(client: httpx.AsyncClient, cfg: dict, chunk: list[str]) -> list[list[float]]:
    prov = cfg["provider"]
    if prov == "openai":
        return await _embed_batch_openai_compat(client, cfg, chunk, PROVIDER_SPECS["openai"]["url"], "openai")
    if prov == "openrouter":
        return await _embed_batch_openai_compat(client, cfg, chunk, PROVIDER_SPECS["openrouter"]["url"], "openrouter")
    if prov == "gemini":
        return await _embed_batch_gemini(client, cfg, chunk)
    raise EmbeddingError(f"Provider no implementado: {prov}")


async def _embed_batch_openai_compat(client, cfg, chunk, url: str, label: str):
    """Request OpenAI-compatible embeddings endpoint (OpenAI y OpenRouter)."""
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    payload: dict = {"model": cfg["model"], "input": chunk}
    # MRL: pedimos dims explicitas cuando el modelo lo soporta (ej: gemini-001)
    if cfg.get("request_dims"):
        payload["dimensions"] = int(cfg["request_dims"])
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(delay); delay = min(delay * 2, 30); continue
            r.raise_for_status()
            data = r.json()
            return [item["embedding"] for item in data["data"]]
        except (httpx.HTTPError, KeyError) as e:
            if attempt == MAX_RETRIES - 1:
                raise EmbeddingError(f"{label} embed fallo: {e}")
            await asyncio.sleep(delay); delay = min(delay * 2, 30)
    raise EmbeddingError(f"{label} embed agoto reintentos")


async def _embed_batch_gemini(client, cfg, chunk):
    """Gemini batchEmbedContents: 1 request, N textos."""
    base = PROVIDER_SPECS["gemini"]["url_base"]
    model = cfg["model"]
    url = f"{base}/models/{model}:batchEmbedContents?key={cfg['api_key']}"
    payload = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": t}]},
            }
            for t in chunk
        ]
    }
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            r = await client.post(url, json=payload)
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(delay); delay = min(delay * 2, 30); continue
            r.raise_for_status()
            data = r.json()
            return [emb["values"] for emb in data.get("embeddings", [])]
        except (httpx.HTTPError, KeyError) as e:
            if attempt == MAX_RETRIES - 1:
                raise EmbeddingError(f"gemini embed fallo: {e}")
            await asyncio.sleep(delay); delay = min(delay * 2, 30)
    raise EmbeddingError("gemini embed agoto reintentos")


async def embed_one(text: str) -> list[float]:
    """Embebe un solo texto. Cache LRU por (provider, text)."""
    if not text or not text.strip():
        return []
    cfg = get_active_config()
    key = f"{cfg['provider']}::{text.strip()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    vecs = await embed_texts([text.strip()])
    if vecs:
        _cache_put(key, vecs[0])
        return vecs[0]
    return []


def to_pgvector(vec: list[float]) -> str:
    """Serializa un vector Python como literal pgvector."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ── Simple LRU en memoria ────────────────────────────────────
_CACHE: dict[str, tuple[float, list[float]]] = {}
_CACHE_MAX = 512
_CACHE_TTL = 3600


def _cache_get(key: str) -> list[float] | None:
    v = _CACHE.get(key)
    if not v:
        return None
    ts, vec = v
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return vec


def _cache_put(key: str, vec: list[float]) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        drop = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: _CACHE_MAX // 5]
        for k, _ in drop:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.time(), vec)


# ── Helpers de dominio ───────────────────────────────────────
def build_insumo_text(name: str, category: str | None = None, subcategory: str | None = None, description: str | None = None) -> str:
    parts: list[str] = [name.strip()]
    if category:
        parts.append(category.replace("_", " "))
    if subcategory:
        parts.append(subcategory.replace("_", " "))
    if description:
        d = description.strip()
        if d:
            parts.append(d[:200])
    return " | ".join(parts)


async def embed_insumo_safe(name: str, category=None, subcategory=None, description=None):
    """Hook tolerante: devuelve None si falla o no hay config."""
    if not is_configured():
        return None
    try:
        txt = build_insumo_text(name, category, subcategory, description)
        vec = await embed_one(txt)
        return vec or None
    except Exception as e:
        print(f"[embed_insumo_safe] fallo: {e}")
        return None
