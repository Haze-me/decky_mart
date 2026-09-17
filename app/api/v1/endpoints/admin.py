import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.kyc_document import KYCDocument, KYCReviewStatus
from app.models.otp import OTPPurpose
from app.models.solver_profile import SolverProfile
from app.models.user import AccountStatus, User, UserRole
from app.schemas.admin import (
    AdminLoginRequest,
    AdminUserDetailResponse,
    CreateAdminRequest,
    CreateAdminResponse,
    KYCDocumentDetail,
    ReviewAction,
    ReviewRequest,
    ReviewResponse,
    SolverListItem,
    SolverListResponse,
    SolverProfileDetail,
)
from app.schemas.auth import LoginResponse
from app.services.email import send_review_result_email
from app.services.otp_service import issue_otp
from app.services.session_service import issue_login_session
from app.services.storage import build_public_url, generate_presigned_get_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["admin"])


@router.post("/admin/create-admin", response_model=CreateAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    payload: CreateAdminRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    new_admin = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.ADMIN,
        account_status=AccountStatus.PENDING_EMAIL_VERIFICATION,
    )
    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)

    await issue_otp(new_admin, OTPPurpose.EMAIL_VERIFICATION, db)

    return CreateAdminResponse(
        id=new_admin.id,
        email=new_admin.email,
        full_name=new_admin.full_name,
        account_status=new_admin.account_status,
        message="Admin account created. They must verify their email via /auth/verify-email to activate it.",
    )


@router.post("/admin/login", response_model=LoginResponse)
async def admin_login(payload: AdminLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an admin account")

    if user.account_status == AccountStatus.PENDING_EMAIL_VERIFICATION:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in")

    await issue_login_session(user, response, db)

    return LoginResponse(id=user.id, email=user.email, role=user.role, account_status=user.account_status, message="Admin login successful")


@router.get("/admin/solvers", response_model=SolverListResponse)
async def list_solvers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str = Query("pending_review", alias="status", description="account_status value, or 'all'"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    base_query = select(User).where(User.role == UserRole.SOLVER)
    count_query = select(func.count()).select_from(User).where(User.role == UserRole.SOLVER)

    if status_filter != "all":
        try:
            status_enum = AccountStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
        base_query = base_query.where(User.account_status == status_enum)
        count_query = count_query.where(User.account_status == status_enum)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * limit
    result = await db.execute(base_query.order_by(User.created_at.desc()).offset(offset).limit(limit))
    users = result.scalars().all()

    solver_items = []
    for u in users:
        profile_result = await db.execute(select(SolverProfile).where(SolverProfile.user_id == u.id))
        profile = profile_result.scalar_one_or_none()
        solver_items.append(
            SolverListItem(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                phone_number=u.phone_number,
                category=profile.category if profile else None,
                state=profile.state if profile else None,
                account_status=u.account_status,
                created_at=u.created_at,
            )
        )

    return SolverListResponse(total=total, page=page, limit=limit, solvers=solver_items)


@router.get("/user/{user_id}", response_model=AdminUserDetailResponse)
async def get_user_by_id(
    user_id: uuid.UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    profile_result = await db.execute(select(SolverProfile).where(SolverProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()

    kyc_result = await db.execute(select(KYCDocument).where(KYCDocument.user_id == user_id))
    kyc = kyc_result.scalar_one_or_none()

    solver_profile_detail = None
    if profile:
        solver_profile_detail = SolverProfileDetail(
            profile_image_url=build_public_url(profile.profile_image_key),
            contact_address=profile.contact_address,
            shop_address=profile.shop_address,
            state=profile.state,
            nationality=profile.nationality,
            category=profile.category,
            description=profile.description,
            skills=profile.skills,
            latitude=profile.latitude,
            longitude=profile.longitude,
            radius_km=profile.radius_km,
            working_experience=profile.working_experience,
            availability=profile.availability,
            pricing_guidance=profile.pricing_guidance,
            response_time=profile.response_time,
            bank_name=profile.bank_name,
            acct_num=profile.acct_num,
            acct_name=profile.acct_name,
        )

    kyc_document_detail = None
    if kyc:
        kyc_document_detail = KYCDocumentDetail(
            id_document_url=generate_presigned_get_url(kyc.id_document_key),
            selfie_url=generate_presigned_get_url(kyc.selfie_key),
            review_status=kyc.review_status,
            reviewed_by=kyc.reviewed_by,
            reviewed_at=kyc.reviewed_at,
            rejection_reason=kyc.rejection_reason,
        )

    return AdminUserDetailResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=user.role,
        account_status=user.account_status,
        created_at=user.created_at,
        solver_profile=solver_profile_detail,
        kyc_document=kyc_document_detail,
    )


@router.patch("/user/{user_id}/review", response_model=ReviewResponse)
async def review_solver(
    user_id: uuid.UUID,
    payload: ReviewRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.account_status != AccountStatus.PENDING_REVIEW:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is not pending review")

    kyc_result = await db.execute(select(KYCDocument).where(KYCDocument.user_id == user_id))
    kyc = kyc_result.scalar_one_or_none()
    if not kyc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KYC record not found")

    now = datetime.now(timezone.utc)
    approved = payload.action == ReviewAction.APPROVE

    if approved:
        user.account_status = AccountStatus.ACTIVE
        kyc.review_status = KYCReviewStatus.APPROVED
        kyc.rejection_reason = None
    else:
        user.account_status = AccountStatus.REJECTED
        kyc.review_status = KYCReviewStatus.REJECTED
        kyc.rejection_reason = payload.rejection_reason

    kyc.reviewed_by = current_admin.id
    kyc.reviewed_at = now

    await db.commit()

    try:
        send_review_result_email(user.email, approved, payload.rejection_reason)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send review result email to %s: %s", user.email, exc)

    return ReviewResponse(id=user.id, account_status=user.account_status, message=f"User {'approved' if approved else 'rejected'}")