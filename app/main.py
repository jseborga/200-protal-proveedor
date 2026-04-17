import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select, text

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
    """Seed initial categories and units of measure if tables are empty."""
    from app.models.catalog import Category, UnitOfMeasure

    async with async_session() as db:
        cat_count = (await db.execute(select(Category.id).limit(1))).first()
        if not cat_count:
            categories = [
                ("ferreteria", "Ferreteria", "&#128295;", 1),
                ("agregados", "Agregados", "&#9968;", 2),
                ("acero", "Acero", "&#128681;", 3),
                ("electrico", "Electrico", "&#9889;", 4),
                ("sanitario", "Sanitario", "&#128703;", 5),
                ("madera", "Madera", "&#127795;", 6),
                ("cemento", "Cemento", "&#127959;", 7),
                ("pintura", "Pintura", "&#127912;", 8),
                ("ceramica", "Ceramica", "&#129521;", 9),
                ("herramientas", "Herramientas", "&#128736;", 10),
                ("plomeria", "Plomeria", "&#128688;", 11),
                ("vidrios", "Vidrios", "&#129695;", 12),
                ("impermeabilizantes", "Impermeabilizantes", "&#128167;", 13),
                ("aislantes", "Aislantes", "&#129535;", 14),
                ("prefabricados", "Prefabricados", "&#127975;", 15),
                ("seguridad", "Seguridad Industrial", "&#9937;", 16),
                ("maquinaria", "Maquinaria y Equipos", "&#128755;", 17),
                ("techos", "Techos y Cubiertas", "&#127968;", 18),
            ]
            for key, label, icon, order in categories:
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

# Rate limiting (anti-scraping)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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
# Middleware: prevent browser caching of critical assets (sw.js, app.js, app.css)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest


class NoCacheAssetsMiddleware(BaseHTTPMiddleware):
    """Cabeceras de cache para assets criticos y endpoints publicos.

    - Assets del SPA: no-cache (siempre revalidar)
    - Endpoints publicos de datos: cache corto (permite CDN absorber scraping)
    """

    NO_CACHE_PATHS = {"/sw.js", "/assets/app.js", "/assets/app.css", "/"}
    PUBLIC_DATA_PREFIXES = (
        "/api/v1/prices/public",
        "/api/v1/suppliers/public",
        "/api/v1/site-config",
    )

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        path = request.url.path
        if path in self.NO_CACHE_PATHS:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif request.method == "GET" and path.startswith(self.PUBLIC_DATA_PREFIXES):
            # 60s de cache publico, 5min para CDN con stale-while-revalidate
            response.headers["Cache-Control"] = (
                "public, max-age=60, s-maxage=300, stale-while-revalidate=60"
            )
        return response


app.add_middleware(NoCacheAssetsMiddleware)

# Mount frontend (after API routes so /api/* takes priority)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
