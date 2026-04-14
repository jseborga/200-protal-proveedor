from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Dependency: extracts user from JWT bearer token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="No autenticado")

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token invalido")

    from app.models.user import User
    result = await db.execute(select(User).where(User.id == int(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Dependency: returns user or None (for public + auth endpoints)."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
):
    """Dependency: verifies X-API-Key header against DB keys and env fallback."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key requerida")

    # Fallback: env var for backwards compat / bootstrap
    if settings.admin_api_key and api_key == settings.admin_api_key:
        return {"role": "admin", "key_id": None, "scopes": ["read", "write", "delete"]}

    # DB lookup by hash
    from app.models.api_key import ApiKey
    from datetime import datetime, timezone

    key_hash = pwd_context.hash(api_key) if False else None  # skip — compare below
    # Since bcrypt is slow for lookups, use prefix + verify pattern
    key_prefix = api_key[:8]
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_prefix == key_prefix, ApiKey.is_active == True)
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        if pwd_context.verify(api_key, candidate.key_hash):
            # Check expiration
            if candidate.expires_at and candidate.expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=403, detail="API key expirada")

            # Update usage tracking
            candidate.last_used_at = datetime.now(timezone.utc)
            candidate.usage_count += 1
            await db.flush()

            scopes = [s.strip() for s in (candidate.scopes or "read").split(",")]
            return {"role": "integration", "key_id": candidate.id, "scopes": scopes, "name": candidate.name}

    raise HTTPException(status_code=403, detail="API key invalida")
