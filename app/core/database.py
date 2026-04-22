from urllib.parse import parse_qsl, urlencode

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings


_DISALLOWED_QUERY_PARAMS = {"sslmode"}


def _clean_url(url: str) -> str:
    """Elimina parametros que asyncpg no soporta (sslmode, etc.).

    No usa urlparse+urlunparse para evitar corromper URLs de sqlite
    (p.ej. sqlite+aiosqlite:///:memory: se colapsa a :/:memory:).
    En su lugar separa el query string por '?' y lo reconstruye.
    """
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    pairs = [
        (k, v) for k, v in parse_qsl(query, keep_blank_values=True)
        if k not in _DISALLOWED_QUERY_PARAMS
    ]
    if not pairs:
        return base
    return f"{base}?{urlencode(pairs)}"


_clean_database_url = _clean_url(settings.database_url)

# SQLite usa StaticPool/NullPool y no acepta pool_size/max_overflow.
_engine_kwargs: dict = {"echo": settings.app_debug}
if not _clean_database_url.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 20
    _engine_kwargs["max_overflow"] = 10

engine = create_async_engine(_clean_database_url, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Dependency: yields a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
