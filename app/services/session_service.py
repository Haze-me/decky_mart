import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.cookies import set_auth_cookies
from app.core.csrf import generate_csrf_token, set_csrf_cookie
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.user import User


async def issue_login_session(user: User, response: Response, db: AsyncSession) -> None:
    access_token = create_access_token(str(user.id))
    refresh_token_plain = generate_refresh_token()

    refresh_row = RefreshToken(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash=hash_refresh_token(refresh_token_plain),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_row)
    await db.commit()

    set_auth_cookies(response, access_token, refresh_token_plain)
    set_csrf_cookie(response, generate_csrf_token())