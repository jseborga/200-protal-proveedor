"""Pytest fixtures for auditing the WhatsApp conversation flow.

Usa SQLite in-memory para no depender de Postgres en los tests.
Solo crea las tablas necesarias para el hub de conversaciones (pedido, user,
session, message).
"""
import os
import sys
from pathlib import Path

# Asegurar que `app.*` sea importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Evitar cargar .env real. Los tests montan su propio engine SQLite via el
# fixture `engine` y hacen override de get_db; este URL sólo se usa si algo
# importa app.core.database antes del override.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Importar modelos (registra metadata)
from app.models.base import Base
from app.models import pedido as _pedido_mod  # noqa: F401
from app.models import user as _user_mod  # noqa: F401
from app.models import conversation as _conv_mod  # noqa: F401
from app.models import company as _company_mod  # noqa: F401
from app.models.pedido import Pedido
from app.models.user import User
from app.models.conversation import ConversationSession, Message
from app.models.session_tag import Tag, SessionTag


@pytest_asyncio.fixture
async def engine():
    """SQLite in-memory engine; crea solo las tablas del hub.

    Nota: SQLite solo hace AUTOINCREMENT con columnas INTEGER, no BIGINT.
    Para que Message.id autoincremente forzamos el tipo efectivo a INTEGER
    durante los tests (el modelo en prod usa BigInteger en Postgres).
    """
    from sqlalchemy import Integer
    Message.__table__.c.id.type = Integer()

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(lambda sync_conn: User.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: Pedido.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: ConversationSession.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: Message.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: Tag.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: SessionTag.__table__.create(sync_conn, checkfirst=True))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    """Sesión SQLAlchemy lista para usar en cada test."""
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def sample_user(db) -> User:
    u = User(
        email="cliente@test.com",
        hashed_password="x",
        full_name="Cliente Test",
        role="buyer",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def sample_pedido(db, sample_user) -> Pedido:
    p = Pedido(
        reference="PED-0001",
        title="Cotización de cemento",
        description="Compra para obra",
        state="active",
        created_by=sample_user.id,
        currency="BOB",
        client_whatsapp="+591 71234567",
        item_count=0,
        quotes_received=0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest_asyncio.fixture
async def sample_session(db, sample_pedido) -> ConversationSession:
    s = ConversationSession(
        pedido_id=sample_pedido.id,
        client_user_id=sample_pedido.created_by,
        client_phone="59171234567",
        state="waiting_first_contact",
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s
