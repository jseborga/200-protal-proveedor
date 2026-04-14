"""Common FastAPI dependencies for route handlers."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional, verify_api_key
from app.models.user import User

# Roles: admin > manager > field_agent > user / supplier
STAFF_ROLES = ("admin", "superadmin", "manager", "field_agent")
MANAGER_ROLES = ("admin", "superadmin", "manager")
ADMIN_ROLES = ("admin", "superadmin")


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return user


async def require_manager(user: User = Depends(get_current_user)) -> User:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de gestor",
        )
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """Admin, manager, or field_agent — anyone who can do data entry."""
    if user.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de personal",
        )
    return user
