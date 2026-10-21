import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_otp_code, hash_otp
from app.models.otp import OTP, OTPPurpose
from app.models.user import User
from app.services.email import send_otp_email
from sqlalchemy import update

logger = logging.getLogger(__name__)


async def issue_otp(user: User, purpose: OTPPurpose, db: AsyncSession) -> None:
    await db.execute(
        update(OTP)
        .where(OTP.user_id == user.id, OTP.purpose == purpose, OTP.is_used == False)
        .values(is_used=True)
    )

    code = generate_otp_code()
    otp = OTP(
        user_id=user.id,
        code_hash=hash_otp(code),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp)
    await db.commit()

    try:
        send_otp_email(user.email, code, purpose.value)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send OTP email to user %s: %s", user.id, exc)