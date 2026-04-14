"""Motor de matching semantico de 4 niveles.

Vincula nombres de producto de proveedor con insumos estandarizados:
1. Remembered: matches previos validados para el mismo proveedor
2. Exact: nombre normalizado identico
3. Trigram: similaridad pg_trgm > umbral
4. Fuzzy: overlap de tokens (Jaccard)
"""

import re
import unicodedata

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insumo import Insumo
from app.models.match import ProductMatch
from app.models.quotation import Quotation, QuotationLine

# ── Config ──────────────────────────────────────────────────────
TRIGRAM_THRESHOLD = 0.3
FUZZY_THRESHOLD = 0.4
MIN_CONFIDENCE_AUTO = 0.6

STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "en", "con", "para", "por",
    "un", "una", "unos", "unas", "y", "o", "a", "al",
    "tipo", "clase", "calidad", "marca", "similar",
}

# Fallback hardcoded — used when DB is unavailable (tests, CLI tools)
_FALLBACK_UOM_MAP = {
    "m3": "m3", "metro cubico": "m3", "metros cubicos": "m3", "m³": "m3",
    "m2": "m2", "metro cuadrado": "m2", "metros cuadrados": "m2", "m²": "m2",
    "ml": "ml", "metro lineal": "ml", "metros lineales": "ml", "m": "ml",
    "kg": "kg", "kilogramo": "kg", "kilogramos": "kg", "kilo": "kg", "kilos": "kg",
    "tn": "tn", "tonelada": "tn", "toneladas": "tn", "ton": "tn",
    "pza": "pza", "pieza": "pza", "piezas": "pza", "unidad": "pza", "und": "pza", "u": "pza",
    "bls": "bls", "bolsa": "bls", "bolsas": "bls",
    "lt": "lt", "litro": "lt", "litros": "lt", "l": "lt",
    "gl": "gl", "galon": "gl", "galones": "gl",
    "rollo": "rollo", "rollos": "rollo",
    "pliego": "pliego", "pliegos": "pliego",
    "lata": "lata", "latas": "lata",
    "global": "glb", "glb": "glb",
}

# Cached UOM map built from DB — refreshed on first use and on demand
_db_uom_map: dict[str, str] | None = None


async def build_uom_map_from_db(db: AsyncSession) -> dict[str, str]:
    """Build UOM alias map from the mkt_uom table."""
    global _db_uom_map
    from app.models.catalog import UnitOfMeasure

    result = await db.execute(
        select(UnitOfMeasure).where(UnitOfMeasure.is_active == True)
    )
    uom_map = {}
    for uom in result.scalars().all():
        uom_map[uom.key] = uom.key
        for alias in (uom.aliases or []):
            uom_map[alias.lower().strip()] = uom.key
    _db_uom_map = uom_map
    return uom_map


def get_uom_map() -> dict[str, str]:
    """Return the current UOM map (DB-backed if loaded, fallback otherwise)."""
    return _db_uom_map if _db_uom_map is not None else _FALLBACK_UOM_MAP

MEASURE_RE = re.compile(
    r'\b(\d+(?:[.,]\d+)?)\s*(?:x\s*(\d+(?:[.,]\d+)?)\s*(?:x\s*(\d+(?:[.,]\d+)?))?)?\s*'
    r'(mm|cm|m|pulg|pulgadas?|")\b',
    re.IGNORECASE,
)


# ── Text normalization ──────────────────────────────────────────
def normalize_text(text_val: str) -> str:
    """Normalize text for matching: lowercase, no accents, no special chars."""
    text_val = text_val.lower().strip()
    # Remove accents
    text_val = unicodedata.normalize("NFKD", text_val)
    text_val = "".join(c for c in text_val if not unicodedata.combining(c))
    # Remove special characters except alphanumeric and spaces
    text_val = re.sub(r"[^\w\s]", " ", text_val)
    # Collapse whitespace
    text_val = re.sub(r"\s+", " ", text_val).strip()
    return text_val


def normalize_uom(uom: str) -> str:
    """Normalize unit of measure."""
    key = uom.lower().strip().rstrip(".")
    return get_uom_map().get(key, key)


def tokenize(text_val: str) -> set[str]:
    """Split normalized text into meaningful tokens."""
    tokens = set(normalize_text(text_val).split())
    return tokens - STOPWORDS


# ── Matching engine ─────────────────────────────────────────────
async def run_matching(db: AsyncSession, quotation_id: int) -> int:
    """Run 4-level matching on all lines of a quotation. Returns count of matched lines."""
    # Ensure UOM map is loaded from DB
    if _db_uom_map is None:
        await build_uom_map_from_db(db)

    result = await db.execute(
        select(Quotation).where(Quotation.id == quotation_id)
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        return 0

    lines_result = await db.execute(
        select(QuotationLine).where(QuotationLine.quotation_id == quotation_id)
    )
    lines = lines_result.scalars().all()
    matched = 0

    for line in lines:
        match = await _match_line(db, line, quotation.supplier_id)
        if match:
            line.insumo_id = match["insumo_id"]
            line.match_confidence = match["confidence"]
            line.match_method = match["method"]
            line.match_state = "auto_matched" if match["confidence"] >= MIN_CONFIDENCE_AUTO else "pending"
            matched += 1

    return matched


async def _match_line(db: AsyncSession, line: QuotationLine, supplier_id: int) -> dict | None:
    """Try matching a single line through 4 levels."""
    name_norm = normalize_text(line.product_name)

    # Level 1: Remembered matches
    result = await _match_remembered(db, supplier_id, name_norm)
    if result:
        return result

    # Level 2: Exact normalized name
    result = await _match_exact(db, name_norm)
    if result:
        return result

    # Level 3: Trigram similarity (pg_trgm)
    result = await _match_trigram(db, name_norm)
    if result:
        return result

    # Level 4: Fuzzy token overlap (Jaccard)
    result = await _match_fuzzy(db, line.product_name)
    if result:
        return result

    return None


async def _match_remembered(db: AsyncSession, supplier_id: int, name_norm: str) -> dict | None:
    """Level 1: Check if we already matched this supplier+product before."""
    result = await db.execute(
        select(ProductMatch).where(
            ProductMatch.supplier_id == supplier_id,
            ProductMatch.product_name_normalized == name_norm,
            ProductMatch.is_validated == True,
        ).order_by(ProductMatch.usage_count.desc()).limit(1)
    )
    match = result.scalar_one_or_none()
    if match:
        match.usage_count += 1
        return {"insumo_id": match.insumo_id, "confidence": 1.0, "method": "remembered"}
    return None


async def _match_exact(db: AsyncSession, name_norm: str) -> dict | None:
    """Level 2: Exact match on normalized insumo name."""
    result = await db.execute(
        select(Insumo).where(
            Insumo.name_normalized == name_norm,
            Insumo.is_active == True,
        ).limit(1)
    )
    insumo = result.scalar_one_or_none()
    if insumo:
        return {"insumo_id": insumo.id, "confidence": 0.95, "method": "exact"}
    return None


async def _match_trigram(db: AsyncSession, name_norm: str) -> dict | None:
    """Level 3: pg_trgm similarity search."""
    result = await db.execute(
        text("""
            SELECT id, name, similarity(name_normalized, :q) AS sim
            FROM mkt_insumo
            WHERE is_active = true
              AND similarity(name_normalized, :q) > :threshold
            ORDER BY sim DESC
            LIMIT 1
        """),
        {"q": name_norm, "threshold": TRIGRAM_THRESHOLD},
    )
    row = result.mappings().first()
    if row:
        return {"insumo_id": row["id"], "confidence": float(row["sim"]), "method": "trigram"}
    return None


async def _match_fuzzy(db: AsyncSession, product_name: str) -> dict | None:
    """Level 4: Jaccard token overlap."""
    query_tokens = tokenize(product_name)
    if len(query_tokens) < 2:
        return None

    # Fetch candidate insumos
    result = await db.execute(
        select(Insumo).where(Insumo.is_active == True)
    )
    insumos = result.scalars().all()

    best_match = None
    best_score = 0.0

    for insumo in insumos:
        insumo_tokens = tokenize(insumo.name)
        if not insumo_tokens:
            continue

        intersection = query_tokens & insumo_tokens
        union = query_tokens | insumo_tokens
        jaccard = len(intersection) / len(union) if union else 0

        if jaccard > best_score and jaccard >= FUZZY_THRESHOLD:
            best_score = jaccard
            best_match = insumo

    if best_match:
        return {"insumo_id": best_match.id, "confidence": best_score, "method": "fuzzy"}
    return None
