import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import engine, async_session
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
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ──────────────────────────────────────────────────
from app.api.routes import auth, suppliers, quotations, prices, rfq, webhooks, admin, integration, groups  # noqa: E402

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(suppliers.router, prefix="/api/v1/suppliers", tags=["Suppliers"])
app.include_router(quotations.router, prefix="/api/v1/quotations", tags=["Quotations"])
app.include_router(prices.router, prefix="/api/v1/prices", tags=["Prices"])
app.include_router(rfq.router, prefix="/api/v1/rfq", tags=["RFQ"])
app.include_router(webhooks.router, prefix="/api/v1/webhook", tags=["Webhooks"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(integration.router, prefix="/api/v1/integration", tags=["Integration"])
app.include_router(groups.router, prefix="/api/v1/groups", tags=["Groups"])


# ── Health ──────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "app": settings.app_name, "env": settings.app_env}


# ── Static / SPA ────────────────────────────────────────────────
# Mount frontend (after API routes so /api/* takes priority)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
