"""Servicio de embeddings (OpenAI text-embedding-3-small por default).

Wrapper minimal sobre la API de OpenAI con:
  - batch embeddings (hasta 100 por request)
  - cache en memoria LRU para queries repetidas
  - reintentos con backoff exponencial
  - formato pgvector-compatible (string "[v1,v2,...]") para insert/update
"""

from __future__ import annotations

import asyncio
import time
from functools import lru_cache
from typing import Iterable

import httpx

from app.core.config import settings

OPENAI_URL = "https://api.openai.com/v1/embeddings"
MAX_BATCH = 100
MAX_RETRIES = 4


class EmbeddingError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embebe una lista de textos. Devuelve lista de vectores del mismo largo."""
    if not settings.embedding_api_key:
        raise EmbeddingError("EMBEDDING_API_KEY no configurada")
    if not texts:
        return []

    # Batches
    out: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(texts), MAX_BATCH):
            chunk = texts[i:i + MAX_BATCH]
            vecs = await _embed_batch(client, chunk)
            out.extend(vecs)
    return out


async def _embed_batch(client: httpx.AsyncClient, chunk: list[str]) -> list[list[float]]:
    payload = {"model": settings.embedding_model, "input": chunk}
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            r = await client.post(OPENAI_URL, headers=_headers(), json=payload)
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            r.raise_for_status()
            data = r.json()
            # OpenAI returns items in input order
            return [item["embedding"] for item in data["data"]]
        except (httpx.HTTPError, KeyError) as e:
            if attempt == MAX_RETRIES - 1:
                raise EmbeddingError(f"embed batch fallo: {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    raise EmbeddingError("embed batch agoto reintentos")


async def embed_one(text: str) -> list[float]:
    """Embebe un solo texto. Usa cache LRU por el string exacto."""
    if not text or not text.strip():
        return []
    cached = _cache_get(text.strip())
    if cached is not None:
        return cached
    vecs = await embed_texts([text.strip()])
    if vecs:
        _cache_put(text.strip(), vecs[0])
        return vecs[0]
    return []


def to_pgvector(vec: list[float]) -> str:
    """Serializa un vector Python como literal pgvector."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ── Simple LRU en memoria para queries de usuarios ────────────
_CACHE: dict[str, tuple[float, list[float]]] = {}
_CACHE_MAX = 512
_CACHE_TTL = 3600  # 1h


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
        # Drop ~oldest 20%
        drop = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: _CACHE_MAX // 5]
        for k, _ in drop:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.time(), vec)


def is_configured() -> bool:
    return bool(settings.embedding_api_key)


def build_insumo_text(name: str, category: str | None = None, subcategory: str | None = None, description: str | None = None) -> str:
    """Compone el texto a embeber de un insumo.

    Incluye nombre + categoria + subcategoria + descripcion breve para
    darle contexto al modelo. El orden importa: el nombre pesa mas al inicio.
    """
    parts: list[str] = [name.strip()]
    if category:
        parts.append(category.replace("_", " "))
    if subcategory:
        parts.append(subcategory.replace("_", " "))
    if description:
        # Limitar descripcion a ~200 chars para no diluir el embedding
        d = description.strip()
        if d:
            parts.append(d[:200])
    return " | ".join(parts)


async def embed_insumo_safe(name: str, category: str | None = None, subcategory: str | None = None, description: str | None = None):
    """Embebe un insumo tolerando errores — devuelve None si falla.

    Pensado para usar en hooks post create/update: nunca debe romper la request.
    """
    if not is_configured():
        return None
    try:
        text_to_embed = build_insumo_text(name, category, subcategory, description)
        vec = await embed_one(text_to_embed)
        return vec or None
    except Exception as e:
        print(f"[embed_insumo_safe] fallo embeber '{name[:50]}': {e}")
        return None
