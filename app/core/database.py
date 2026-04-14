from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings


def _clean_url(url: str) -> str:
    """Elimina parametros que asyncpg no soporta (sslmode, etc.)."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    # asyncpg no acepta sslmode — removerlo
    params.pop("sslmode", None)
    clean_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))


engine = create_async_engine(
    _clean_url(settings.database_url),
    echo=settings.app_debug,
    pool_size=20,
    max_overflow=10,
)

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
