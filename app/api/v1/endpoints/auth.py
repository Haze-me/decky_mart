import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.cookies import REFRESH_TOKEN_COOKIE, clear_auth_cookies, set_auth_cookies
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_otp_code,
    verify_password,
)
from app.db.session import get_db
from app.models.otp import OTP, OTPPurpose
from app.models.refresh_token import RefreshToken
from app.models.user import AccountStatus, User, UserRole
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyEmailRequest,
    GoogleAuthRequest,
)
from app.schemas.user import RegisterRequest, RegisterResponse, UserMeResponse
from app.services.otp_service import issue_otp
from app.services.session_service import issue_login_session
from app.services.google_auth import GoogleTokenError, verify_google_id_token
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()
    if existing:
        if existing.google_id and not existing.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is registered via Google Sign-In. Please use 'Continue with Google' to log in, or use 'Forgot password' to set a password.",
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.SOLVER,
        account_status=AccountStatus.PENDING_EMAIL_VERIFICATION,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await issue_otp(user, OTPPurpose.EMAIL_VERIFICATION, db)

    return user


@router.post("/verify-email", response_model=LoginResponse)
async def verify_email(payload: VerifyEmailRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if user.account_status != AccountStatus.PENDING_EMAIL_VERIFICATION:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already verified")

    otp_result = await db.execute(
        select(OTP)
        .where(OTP.user_id == user.id, OTP.purpose == OTPPurpose.EMAIL_VERIFICATION, OTP.is_used == False)
        .order_by(OTP.created_at.desc())
    )
    otp = otp_result.scalars().first()

    if not otp:
        raise HTTPException(status_code=400, detail="No active verification code. Request a new one.")

    if datetime.now(timezone.utc) > otp.expires_at:
        raise HTTPException(status_code=400, detail="Verification code expired. Request a new one.")

    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        otp.is_used = True
        await db.commit()
        raise HTTPException(status_code=400, detail="Too many failed attempts. Request a new code.")

    if not verify_otp_code(payload.code, otp.code_hash):
        otp.attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid verification code")

    otp.is_used = True

    if user.role == UserRole.ADMIN:
        user.account_status = AccountStatus.ACTIVE
        message = "Email verified. Your admin account is now active."
    else:
        user.account_status = AccountStatus.PROFILE_INCOMPLETE
        message = "Email verified. You're now logged in — complete your profile to unlock full access."

    await db.commit()

    await issue_login_session(user, response, db)

    return LoginResponse(id=user.id, email=user.email, role=user.role, account_status=user.account_status, message=message)


@router.post("/resend-verification-code", response_model=ResendVerificationResponse)
async def resend_verification_code(payload: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if user.account_status != AccountStatus.PENDING_EMAIL_VERIFICATION:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already verified")

    otp_result = await db.execute(
        select(OTP)
        .where(OTP.user_id == user.id, OTP.purpose == OTPPurpose.EMAIL_VERIFICATION, OTP.is_used == False)
        .order_by(OTP.created_at.desc())
    )
    latest_otp = otp_result.scalars().first()

    if latest_otp:
        elapsed = datetime.now(timezone.utc) - latest_otp.created_at
        if elapsed < timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS):
            wait = settings.OTP_RESEND_COOLDOWN_SECONDS - int(elapsed.total_seconds())
            raise HTTPException(status_code=429, detail=f"Please wait {wait}s before requesting another code")

    await issue_otp(user, OTPPurpose.EMAIL_VERIFICATION, db)

    return ResendVerificationResponse(detail="Verification code resent")


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.google_id and not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This email is registered via Google Sign-In. Please use 'Continue with Google' to log in, or use 'Forgot password' to set a password.",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.account_status == AccountStatus.PENDING_EMAIL_VERIFICATION:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in")

    await issue_login_session(user, response, db)

    return LoginResponse(id=user.id, email=user.email, role=user.role, account_status=user.account_status, message="Login successful")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_tokens(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if stored.is_revoked:
        await db.execute(update(RefreshToken).where(RefreshToken.family_id == stored.family_id).values(is_revoked=True))
        await db.commit()
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid. Please log in again.")

    if datetime.now(timezone.utc) > stored.expires_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    stored.is_revoked = True

    new_raw_token = generate_refresh_token()
    new_row = RefreshToken(
        user_id=stored.user_id,
        family_id=stored.family_id,
        token_hash=hash_refresh_token(new_raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_row)
    await db.commit()

    new_access_token = create_access_token(str(stored.user_id))
    set_auth_cookies(response, new_access_token, new_raw_token)

    return RefreshResponse(detail="Token refreshed")


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        stored = result.scalar_one_or_none()
        if stored:
            stored.is_revoked = True
            await db.commit()

    clear_auth_cookies(response)

    return LogoutResponse(detail="Logged out")


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    generic_response = ForgotPasswordResponse(detail="If an account exists for this email, a reset code has been sent.")

    if not user:
        return generic_response

    otp_result = await db.execute(
        select(OTP)
        .where(OTP.user_id == user.id, OTP.purpose == OTPPurpose.PASSWORD_RESET, OTP.is_used == False)
        .order_by(OTP.created_at.desc())
    )
    latest_otp = otp_result.scalars().first()

    if latest_otp:
        elapsed = datetime.now(timezone.utc) - latest_otp.created_at
        if elapsed < timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS):
            return generic_response

    await issue_otp(user, OTPPurpose.PASSWORD_RESET, db)

    return generic_response


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    otp_result = await db.execute(
        select(OTP)
        .where(OTP.user_id == user.id, OTP.purpose == OTPPurpose.PASSWORD_RESET, OTP.is_used == False)
        .order_by(OTP.created_at.desc())
    )
    otp = otp_result.scalars().first()

    if not otp:
        raise HTTPException(status_code=400, detail="No active reset code. Request a new one.")

    if datetime.now(timezone.utc) > otp.expires_at:
        raise HTTPException(status_code=400, detail="Reset code expired. Request a new one.")

    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        otp.is_used = True
        await db.commit()
        raise HTTPException(status_code=400, detail="Too many failed attempts. Request a new code.")

    if not verify_otp_code(payload.code, otp.code_hash):
        otp.attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid reset code")

    otp.is_used = True
    user.hashed_password = hash_password(payload.new_password)

    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.is_revoked == False).values(is_revoked=True)
    )

    await db.commit()

    return ResetPasswordResponse(detail="Password reset successful. Please log in again.")


@router.get("/user", response_model=UserMeResponse)
async def get_own_user(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/google", response_model=LoginResponse)
async def google_auth(payload: GoogleAuthRequest, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        google_data = verify_google_id_token(payload.id_token)
    except GoogleTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {exc}")

    google_id = google_data["sub"]
    email = google_data["email"]
    full_name = google_data.get("name")

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.role != UserRole.SOLVER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Google sign-in is only available for Solver accounts",
                )
            existing_user.google_id = google_id
            user = existing_user
        else:
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=None,
                google_id=google_id,
                role=UserRole.SOLVER,
                account_status=AccountStatus.PROFILE_INCOMPLETE,
            )
            db.add(user)

        await db.commit()
        await db.refresh(user)

    await issue_login_session(user, response, db)

    return LoginResponse(
        id=user.id, email=user.email, role=user.role, account_status=user.account_status, message="Google sign-in successful"
    )