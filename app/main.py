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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await _init_db()
    await _ensure_superadmin()
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
from app.api.routes import auth, suppliers, quotations, prices, rfq, webhooks, admin, integration  # noqa: E402

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(suppliers.router, prefix="/api/v1/suppliers", tags=["Suppliers"])
app.include_router(quotations.router, prefix="/api/v1/quotations", tags=["Quotations"])
app.include_router(prices.router, prefix="/api/v1/prices", tags=["Prices"])
app.include_router(rfq.router, prefix="/api/v1/rfq", tags=["RFQ"])
app.include_router(webhooks.router, prefix="/api/v1/webhook", tags=["Webhooks"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(integration.router, prefix="/api/v1/integration", tags=["Integration"])


# ── Health ──────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "app": settings.app_name, "env": settings.app_env}


# ── Static / SPA ────────────────────────────────────────────────
# Mount frontend (after API routes so /api/* takes priority)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
