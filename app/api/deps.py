import uuid

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actors import Actor
from app.core.config import settings
from app.db.session import get_db
from app.models.user import AccountStatus, User, UserRole

CUSTOMER_ACCESS_COOKIE = "cust_access"
CUSTOMER_TOKEN_ISSUER = "customer-service"

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("scope") != "access":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token scope")

    result = await db.execute(select(User).where(User.id == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.account_status == AccountStatus.BANNED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been banned")

    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def ensure_not_suspended(user: User) -> None:
    if user.account_status == AccountStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your account is suspended: {user.status_reason or 'contact support for details'}",
        )


async def _try_local_actor(request: Request, db: AsyncSession) -> Actor | None:
    token = request.cookies.get("access_token")
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

    if payload.get("scope") != "access":
        return None

    result = await db.execute(select(User).where(User.id == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user or user.account_status == AccountStatus.BANNED:
        return None

    return Actor(actor_type=user.role, actor_id=user.id, user=user, display_name=user.full_name)


def _try_customer_actor(request: Request) -> Actor | None:
    token = request.cookies.get(CUSTOMER_ACCESS_COOKIE)
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.CUSTOMER_TOKEN_SIGNING_KEY,
            algorithms=["HS256"],
            issuer=CUSTOMER_TOKEN_ISSUER,
        )
    except JWTError:
        return None

    if payload.get("scope") != "access":
        return None

    try:
        customer_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        return None

    return Actor(
        actor_type=UserRole.CUSTOMER,
        actor_id=customer_id,
        display_name=payload.get("full_name"),
        avatar_url=payload.get("avatar_url"),
    )


async def get_current_actor(request: Request, db: AsyncSession = Depends(get_db)) -> Actor:
    """Resolves a comment/reaction author: tries our own solver/admin session first, then the
    customer service's token. NOTE: a customer whose password was just reset or who was just
    deactivated can still pass here for up to 15 minutes (their token's remaining lifetime) —
    we have no local revocation check for tokens we didn't issue. Accepted trade-off, not a bug.
    """
    actor = await _try_local_actor(request, db)
    if actor:
        return actor

    actor = _try_customer_actor(request)
    if actor:
        return actor

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_optional_actor(request: Request, db: AsyncSession = Depends(get_db)) -> Actor | None:
    """Same resolution as get_current_actor, but returns None instead of 401 — for public
    endpoints (the feed) that still want to show the viewer's own reaction when they're logged in.
    """
    actor = await _try_local_actor(request, db)
    if actor:
        return actor
    return _try_customer_actor(request)


async def get_active_solver(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.SOLVER or current_user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only active solvers can do this",
        )
    return current_user
