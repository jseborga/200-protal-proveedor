import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, text

from app.core.banlist import BanCheckMiddleware
from app.core.config import settings
from app.core.database import engine, async_session
from app.core.rate_limit import limiter
from app.models.base import Base


async def _init_db():
    """Inicializa la base de datos: extensiones + tablas.

    - Siempre crea extensiones pg_trgm y unaccent (idempotente)
    - Crea tablas faltantes (no destruye datos existentes)
    - Cuando el proyecto crezca, Alembic maneja migraciones incrementales
      y este bloque solo actua como safety net para el primer deploy
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        # pgvector para busqueda semantica de insumos (puede fallar si la extension
        # no esta disponible en la imagen de Postgres; no bloquear el boot)
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as e:
            print(f"[init_db] pgvector no disponible: {e}")
        await conn.run_sync(Base.metadata.create_all)
        # Add columns that create_all won't add to existing tables
        for col, coltype in [("latitude", "DOUBLE PRECISION"), ("longitude", "DOUBLE PRECISION")]:
            await conn.execute(text(
                f"ALTER TABLE mkt_supplier ADD COLUMN IF NOT EXISTS {col} {coltype}"
            ))
        # group_id FK on mkt_insumo for product grouping
        await conn.execute(text(
            "ALTER TABLE mkt_insumo ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES mkt_insumo_group(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mkt_insumo_group_id ON mkt_insumo(group_id)"
        ))
        # Phase 2: company membership on mkt_user
        await conn.execute(text(
            "ALTER TABLE mkt_user ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES mkt_company(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE mkt_user ADD COLUMN IF NOT EXISTS company_role VARCHAR(30)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mkt_user_company_id ON mkt_user(company_id)"
        ))
        # Phase 2: company_id FK on mkt_pedido
        await conn.execute(text(
            "ALTER TABLE mkt_pedido ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES mkt_company(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mkt_pedido_company_id ON mkt_pedido(company_id)"
        ))
        # Supplier enrichment: description, operating_cities, phone2
        await conn.execute(text(
            "ALTER TABLE mkt_supplier ADD COLUMN IF NOT EXISTS description TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE mkt_supplier ADD COLUMN IF NOT EXISTS operating_cities VARCHAR(50)[]"
        ))
        await conn.execute(text(
            "ALTER TABLE mkt_supplier ADD COLUMN IF NOT EXISTS phone2 VARCHAR(30)"
        ))
        # spec_url for technical specs link on insumos
        await conn.execute(text(
            "ALTER TABLE mkt_insumo ADD COLUMN IF NOT EXISTS spec_url VARCHAR(500)"
        ))
        # image_url for product image (served from /uploads/insumos/)
        await conn.execute(text(
            "ALTER TABLE mkt_insumo ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)"
        ))
        # Featured / subscription tier para priorizar proveedores en listas y mapa
        await conn.execute(text(
            "ALTER TABLE mkt_supplier ADD COLUMN IF NOT EXISTS is_featured BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE mkt_supplier ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20) NOT NULL DEFAULT 'none'"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mkt_supplier_featured ON mkt_supplier(is_featured DESC, rating DESC)"
        ))
        # Embedding column + HNSW index para busqueda semantica (text-embedding-3-small = 1536 dims)
        try:
            await conn.execute(text(
                "ALTER TABLE mkt_insumo ADD COLUMN IF NOT EXISTS embedding vector(1536)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_mkt_insumo_embedding "
                "ON mkt_insumo USING hnsw (embedding vector_cosine_ops)"
            ))
        except Exception as e:
            print(f"[init_db] columna embedding/indice no creados (pgvector ausente?): {e}")


async def _ensure_superadmin():
    """Crea el superadmin si ADMIN_EMAIL y ADMIN_PASSWORD estan configurados
    y el usuario no existe todavia. Si ya existe, actualiza su rol a admin."""
    if not settings.admin_email or not settings.admin_password:
        return

    from app.models.user import User
    from app.core.security import hash_password

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email))
        user = result.scalar_one_or_none()

        if user:
            if user.role != "admin":
                user.role = "admin"
                await db.commit()
        else:
            user = User(
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                full_name=settings.admin_name,
                role="admin",
                is_active=True,
            )
            db.add(user)
            await db.commit()


async def _seed_catalog():
    """Upsert canonical catalog of categories + UoMs. Idempotente.

    Categorias alineadas con las keys que usan los productos (mkt_insumo.category),
    para que los chips del frontend resuelvan label/icon correctamente.
    """
    from app.models.catalog import Category, UnitOfMeasure

    canonical_categories = [
        ("cemento",            "Cemento",                 "&#127959;", 1),
        ("acero",              "Acero",                   "&#128681;", 2),
        ("agregados",          "Agregados",               "&#9968;",   3),
        ("ladrillos",          "Ladrillos",               "&#129684;", 4),
        ("hormigon",           "Hormigon",                "&#9970;",   5),
        ("prefabricados",      "Prefabricados",           "&#127975;", 6),
        ("madera",             "Madera",                  "&#127795;", 7),
        ("techos",             "Techos y Cubiertas",      "&#127968;", 8),
        ("pisos",              "Pisos",                   "&#128511;", 9),
        ("ceramica",           "Ceramica y Revestimiento","&#129521;", 10),
        ("vidrios",            "Vidrios y Aluminio",      "&#129695;", 11),
        ("pinturas",           "Pinturas",                "&#127912;", 12),
        ("adhesivos",          "Adhesivos y Selladores",  "&#129512;", 13),
        ("impermeabilizantes", "Impermeabilizantes",      "&#128167;", 14),
        ("aislantes",          "Aislantes",               "&#129535;", 15),
        ("plomeria",           "Plomeria",                "&#128688;", 16),
        ("sanitario",          "Sanitario",               "&#128703;", 17),
        ("gas",                "Gas",                     "&#128293;", 18),
        ("hvac",               "Climatizacion (HVAC)",    "&#10052;",  19),
        ("electrico",          "Electrico",               "&#9889;",   20),
        ("iluminacion",        "Iluminacion",             "&#128161;", 21),
        ("redes_datos",        "Redes y Datos",           "&#127760;", 22),
        ("ferreteria",         "Ferreteria",              "&#128295;", 23),
        ("fijaciones",         "Fijaciones",              "&#128274;", 24),
        ("herramientas",       "Herramientas",            "&#128736;", 25),
        ("maquinaria",         "Maquinaria",              "&#128755;", 26),
        ("equipos",            "Equipos",                 "&#128295;", 27),
        ("mano_obra",          "Mano de Obra",            "&#129689;", 28),
        ("seguridad",          "Seguridad Industrial",    "&#9937;",   29),
        ("quimicos_concreto",  "Quimicos para Concreto",  "&#129514;", 30),
        ("quimicos_agua",      "Quimicos para Agua",      "&#128167;", 31),
        ("jardineria",         "Jardineria",              "&#127793;", 32),
        ("urbanismo",          "Urbanismo y Vialidad",    "&#128739;", 33),
        ("varios",             "Varios",                  "&#128230;", 99),
    ]

    async with async_session() as db:
        existing = {c.key: c for c in (await db.execute(select(Category))).scalars().all()}
        # Rename legacy "pintura" → "pinturas" para alinear con productos
        if "pintura" in existing and "pinturas" not in existing:
            existing["pintura"].key = "pinturas"
            existing["pinturas"] = existing.pop("pintura")

        for key, label, icon, order in canonical_categories:
            if key in existing:
                c = existing[key]
                c.label = label
                c.icon = icon
                c.sort_order = order
                c.is_active = True
            else:
                db.add(Category(key=key, label=label, icon=icon, sort_order=order))

        uom_count = (await db.execute(select(UnitOfMeasure.id).limit(1))).first()
        if not uom_count:
            units = [
                ("m3", "Metro cubico (m3)", ["metro cubico", "metros cubicos", "m\u00b3"], 1),
                ("m2", "Metro cuadrado (m2)", ["metro cuadrado", "metros cuadrados", "m\u00b2"], 2),
                ("ml", "Metro lineal (ml)", ["metro lineal", "metros lineales", "m"], 3),
                ("kg", "Kilogramo (kg)", ["kilogramo", "kilogramos", "kilo", "kilos"], 4),
                ("tn", "Tonelada (tn)", ["tonelada", "toneladas", "ton"], 5),
                ("pza", "Pieza (pza)", ["pieza", "piezas", "unidad", "und", "u"], 6),
                ("bls", "Bolsa (bls)", ["bolsa", "bolsas"], 7),
                ("lt", "Litro (lt)", ["litro", "litros", "l"], 8),
                ("gl", "Galon (gl)", ["galon", "galones"], 9),
                ("rollo", "Rollo", ["rollos"], 10),
                ("pliego", "Pliego", ["pliegos"], 11),
                ("lata", "Lata", ["latas"], 12),
                ("glb", "Global (glb)", ["global"], 13),
                ("varilla", "Varilla", ["varillas"], 14),
                ("barra", "Barra", ["barras"], 15),
                ("par", "Par", ["pares"], 16),
                ("juego", "Juego", ["juegos", "jgo"], 17),
                ("caja", "Caja", ["cajas"], 18),
                ("saco", "Saco", ["sacos"], 19),
                ("tubo", "Tubo", ["tubos"], 20),
            ]
            for key, label, aliases, order in units:
                db.add(UnitOfMeasure(key=key, label=label, aliases=aliases, sort_order=order))

        await db.commit()

    # Build UOM map cache for matching engine
    from app.services.matching import build_uom_map_from_db
    async with async_session() as db:
        await build_uom_map_from_db(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await _init_db()
    await _ensure_superadmin()
    await _seed_catalog()
    # Load subscription plans into memory cache (seeds defaults if empty)
    from app.core.plans import load_plans_from_db
    async with async_session() as db:
        await load_plans_from_db(db)
    # Load banned IPs into memory cache
    from app.core.banlist import reload_ban_cache
    await reload_ban_cache()
    # Start scheduled tasks (cron jobs)
    from app.core.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    await engine.dispose()


_expose_docs = settings.is_dev or settings.app_debug

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs" if _expose_docs else None,
    redoc_url="/api/redoc" if _expose_docs else None,
    openapi_url="/api/openapi.json" if _expose_docs else None,
    lifespan=lifespan,
)

# Rate limiting (anti-scraping): usamos solo el decorador @limiter.limit
# y el exception handler. SlowAPIMiddleware se omite porque es un
# BaseHTTPMiddleware que apila mal con otros middlewares de Starlette y
# no aporta nada cuando default_limits esta vacio.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Ban list (honeypot + burst detection) - ASGI puro.
app.add_middleware(BanCheckMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ──────────────────────────────────────────────────
from app.api.routes import auth, suppliers, quotations, prices, rfq, webhooks, admin, integration, groups, pedidos, companies, subscriptions, notifications  # noqa: E402

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(suppliers.router, prefix="/api/v1/suppliers", tags=["Suppliers"])
app.include_router(quotations.router, prefix="/api/v1/quotations", tags=["Quotations"])
app.include_router(prices.router, prefix="/api/v1/prices", tags=["Prices"])
app.include_router(rfq.router, prefix="/api/v1/rfq", tags=["RFQ"])
app.include_router(webhooks.router, prefix="/api/v1/webhook", tags=["Webhooks"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(integration.router, prefix="/api/v1/integration", tags=["Integration"])
app.include_router(groups.router, prefix="/api/v1/groups", tags=["Groups"])
app.include_router(pedidos.router, prefix="/api/v1/pedidos", tags=["Pedidos"])
app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])
app.include_router(subscriptions.router, prefix="/api/v1/subscriptions", tags=["Subscriptions"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])


# ── Health ──────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "app": settings.app_name, "env": settings.app_env}


# ── robots.txt (anti-scraping / SEO) ───────────────────────────
_ROBOTS_TXT = """User-agent: *
Allow: /$
Allow: /manifest.json
Allow: /icon.svg
Allow: /assets/
Disallow: /api/
Disallow: /mcp/
Disallow: /api/v1/prices/internal-dump
Disallow: /api/v1/suppliers/export-all
Disallow: /api/v1/admin/full-export

# Bots agresivos / scrapers comerciales
User-agent: GPTBot
Disallow: /
User-agent: CCBot
Disallow: /
User-agent: ClaudeBot
Disallow: /
User-agent: Google-Extended
Disallow: /
User-agent: anthropic-ai
Disallow: /
User-agent: PerplexityBot
Disallow: /
User-agent: Bytespider
Disallow: /
User-agent: AhrefsBot
Disallow: /
User-agent: SemrushBot
Disallow: /
User-agent: MJ12bot
Disallow: /
User-agent: DotBot
Disallow: /
User-agent: DataForSeoBot
Disallow: /
"""


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return PlainTextResponse(_ROBOTS_TXT, media_type="text/plain")


# ── Emergency unban (protegido por APP_SECRET_KEY) ─────────────
# Uso: GET /api/v1/banlist/purge/<APP_SECRET_KEY>
# Borra toda la tabla mkt_banned_ip y recarga la cache en memoria.
@app.get("/api/v1/banlist/purge/{secret}", include_in_schema=False)
async def banlist_purge(secret: str):
    if secret != settings.app_secret_key:
        from fastapi import HTTPException
        raise HTTPException(403, "Invalid secret")
    from sqlalchemy import delete
    from app.models.banned_ip import BannedIP
    from app.core.banlist import reload_ban_cache
    async with async_session() as db:
        result = await db.execute(delete(BannedIP))
        await db.commit()
        removed = result.rowcount or 0
    await reload_ban_cache()
    return {"ok": True, "removed": removed}


# ── One-time data purge (remove after use) ─────────────────────
@app.post("/api/v1/purge/{secret}")
async def purge_data_direct(secret: str):
    """Emergency purge — validates secret against app_secret_key."""
    if secret != settings.app_secret_key:
        from fastapi import HTTPException
        raise HTTPException(403, "Invalid secret")

    from sqlalchemy import text as sql_text
    tables = [
        "mkt_pedido_precio", "mkt_pedido_item", "mkt_pedido",
        "mkt_notification", "mkt_supplier_suggestion", "mkt_product_match",
        "mkt_price_history", "mkt_insumo_regional_price",
        "mkt_quotation_line", "mkt_quotation", "mkt_rfq",
        "mkt_supplier_rubro", "mkt_supplier_branch", "mkt_supplier",
        "mkt_insumo", "mkt_insumo_group",
        "mkt_category", "mkt_unit_of_measure", "mkt_task_log",
    ]
    counts = {}
    for table in tables:
        try:
            async with async_session() as db:
                r = await db.execute(sql_text(f"SELECT COUNT(*) FROM {table}"))
                c = r.scalar() or 0
                if c > 0:
                    await db.execute(sql_text(f"DELETE FROM {table}"))
                    await db.commit()
                    counts[table] = c
        except Exception as e:
            counts[f"{table}_skip"] = str(e)[:60]
    return {"ok": True, "purged": sum(v for v in counts.values() if isinstance(v, int)), "details": counts}


# ── Public site config (SEO, branding) ─────────────────────────
SEO_DEFAULTS = {
    "site_name": "APU Marketplace",
    "site_title": "Precios de Construccion en Bolivia | APU Marketplace",
    "site_description": "Portal de precios unitarios de materiales de construccion en Bolivia. Compara precios, contacta proveedores y cotiza para tus proyectos.",
    "site_keywords": "precios construccion bolivia, materiales construccion, cemento, acero, ferreteria, proveedores, cotizacion, APU",
    "og_image": "",
    "theme_color": "#1e40af",
    "footer_text": "APU Marketplace - Precios de construccion actualizados",
    "analytics_id": "",
    "contact_email": "",
    "contact_whatsapp": "",
}


@app.get("/api/v1/site-config")
@limiter.limit("120/minute")
async def site_config(request: Request):
    """Config publica del sitio (SEO, branding). No requiere auth."""
    from app.models.system_setting import SystemSetting
    async with async_session() as db:
        setting = await db.get(SystemSetting, "seo_config")
        config = dict(SEO_DEFAULTS)
        if setting and setting.value:
            config.update(setting.value)
        return {"ok": True, "data": config}


# ── MCP Server (SSE for Claude Code Routines) ─────────────────
# Mounted at /mcp — Claude Code Routines connect via SSE
try:
    from app.mcp_endpoint import get_mcp_sse_app
    app.mount("/mcp", get_mcp_sse_app())
    print("[MCP] SSE endpoint mounted at /mcp/sse")
except ImportError as e:
    print(f"[MCP] Not available (missing dependency): {e}")
except Exception as e:
    print(f"[MCP] Failed to mount: {e}")

# ── Static / SPA ────────────────────────────────────────────────
# Middleware ASGI puro para cabeceras de cache. Se evita BaseHTTPMiddleware
# porque stackear varios BaseHTTPMiddleware rompe POST con body.


class NoCacheAssetsMiddleware:
    """Cabeceras de cache para assets criticos y endpoints publicos.

    - Assets del SPA: no-cache (siempre revalidar).
    - Endpoints publicos de datos: cache corto (permite CDN absorber scraping).
    """

    NO_CACHE_PATHS = {"/sw.js", "/assets/app.js", "/assets/app.css", "/"}
    PUBLIC_DATA_PREFIXES = (
        "/api/v1/prices/public",
        "/api/v1/suppliers/public",
        "/api/v1/site-config",
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        cache_header: bytes | None = None
        pragma_header: bytes | None = None
        if path in self.NO_CACHE_PATHS:
            cache_header = b"no-cache, must-revalidate"
            pragma_header = b"no-cache"
        elif method == "GET" and path.startswith(self.PUBLIC_DATA_PREFIXES):
            cache_header = b"public, max-age=60, s-maxage=300, stale-while-revalidate=60"

        if cache_header is None:
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Remove any existing Cache-Control / Pragma
                headers = [(k, v) for (k, v) in headers if k.lower() not in (b"cache-control", b"pragma")]
                headers.append((b"cache-control", cache_header))
                if pragma_header is not None:
                    headers.append((b"pragma", pragma_header))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(NoCacheAssetsMiddleware)

# ── SSR SEO: /p/{id} ────────────────────────────────────────────
# Sirve index.html con meta tags y JSON-LD Product inyectados server-side
# para que Google y crawlers de IA indexen cada producto.

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
_index_template: str | None = None


def _load_index_html() -> str:
    global _index_template
    if _index_template is None:
        with open(os.path.join(frontend_dir, "index.html"), encoding="utf-8") as f:
            _index_template = f.read()
    return _index_template


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@app.get("/p/{insumo_id}", response_class=HTMLResponse, include_in_schema=False)
async def product_page(insumo_id: int, request: Request):
    import json as _json
    from app.models.insumo import Insumo

    async with async_session() as db:
        insumo = await db.get(Insumo, insumo_id)
        if not insumo or not insumo.is_active:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

    base_url = str(request.base_url).rstrip("/")
    canonical = f"{base_url}/p/{insumo_id}"
    name = insumo.name
    cat = insumo.category or "construccion"
    price_txt = f"Bs {insumo.ref_price:.2f} / {insumo.uom}" if insumo.ref_price else f"{insumo.uom}"
    title = f"{name} — Precio en Bolivia | Nexo Base"
    desc = (
        insumo.description
        or f"{name} ({cat}) — {price_txt}. Compara precios de {name} en Bolivia y contacta proveedores verificados. Nexo Base."
    )[:300]

    image_abs = f"{base_url}{insumo.image_url}" if insumo.image_url else None

    product_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "category": insumo.category,
        "description": desc,
        "sku": str(insumo.id),
        "brand": {"@type": "Brand", "name": "Nexo Base"},
        "url": canonical,
    }
    if image_abs:
        product_ld["image"] = image_abs
    if insumo.ref_price:
        product_ld["offers"] = {
            "@type": "Offer",
            "priceCurrency": insumo.ref_currency or "BOB",
            "price": round(float(insumo.ref_price), 2),
            "availability": "https://schema.org/InStock",
            "url": canonical,
            "areaServed": "BO",
        }

    html = _load_index_html()
    e_title = _html_escape(title)
    e_desc = _html_escape(desc)
    e_canonical = _html_escape(canonical)

    replacements = [
        ("<title>Nexo Base | Precios y Proveedores de Construccion en Bolivia</title>",
         f"<title>{e_title}</title>"),
        ('<meta name="description" content="Nexo Base es la plataforma boliviana de precios unitarios (APU) y proveedores verificados de materiales de construccion. Compara precios reales de cemento, acero, ceramica, ferreteria y mas; contacta proveedores por WhatsApp y cotiza tus obras en segundos.">',
         f'<meta name="description" content="{e_desc}">'),
        ('<link rel="canonical" href="https://apu-marketplace-app.q8waob.easypanel.host/">',
         f'<link rel="canonical" href="{e_canonical}">'),
        ('<meta property="og:type" content="website">',
         '<meta property="og:type" content="product">'),
        ('<meta property="og:title" content="Nexo Base | Precios y Proveedores de Construccion en Bolivia">',
         f'<meta property="og:title" content="{e_title}">'),
        ('<meta property="og:description" content="Plataforma de precios unitarios (APU) y directorio de proveedores verificados de materiales de construccion en Bolivia. Compara, contacta y cotiza en minutos.">',
         f'<meta property="og:description" content="{e_desc}">'),
        ('<meta property="og:url" content="https://apu-marketplace-app.q8waob.easypanel.host/">',
         f'<meta property="og:url" content="{e_canonical}">'),
        ('<meta name="twitter:title" content="Nexo Base | Precios y Proveedores de Construccion en Bolivia">',
         f'<meta name="twitter:title" content="{e_title}">'),
        ('<meta name="twitter:description" content="Precios unitarios (APU) actualizados y proveedores verificados de materiales de construccion en Bolivia. Compara precios reales y contacta por WhatsApp.">',
         f'<meta name="twitter:description" content="{e_desc}">'),
    ]
    if image_abs:
        e_img = _html_escape(image_abs)
        e_alt = _html_escape(f"{name} - Nexo Base")
        replacements.extend([
            ('<meta property="og:image" content="https://apu-marketplace-app.q8waob.easypanel.host/icon-512.png">',
             f'<meta property="og:image" content="{e_img}">'),
            ('<meta property="og:image:alt" content="Nexo Base - Precios y proveedores de construccion en Bolivia">',
             f'<meta property="og:image:alt" content="{e_alt}">'),
            ('<meta name="twitter:image" content="https://apu-marketplace-app.q8waob.easypanel.host/icon-512.png">',
             f'<meta name="twitter:image" content="{e_img}">'),
        ])
    for old, new in replacements:
        html = html.replace(old, new, 1)

    product_ld_tag = (
        '\n    <!-- Structured Data: Product -->\n'
        '    <script type="application/ld+json">\n'
        f'    {_json.dumps(product_ld, ensure_ascii=False)}\n'
        '    </script>\n</head>'
    )
    html = html.replace("</head>", product_ld_tag, 1)

    return HTMLResponse(content=html)


# Mount uploads dir (persisted via EasyPanel volume if configured)
uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(os.path.join(uploads_dir, "insumos"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Mount frontend (after API routes so /api/* takes priority)
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
