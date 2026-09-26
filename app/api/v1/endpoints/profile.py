from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_not_suspended, get_current_user
from app.db.session import get_db
from app.models.kyc_document import KYCDocument, KYCReviewStatus
from app.models.solver_profile import SolverProfile
from app.models.user import AccountStatus, User
from app.schemas.profile import (
    ProfileDetailResponse,
    ProfileKYCDetail,
    ProfileSolverDetail,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)
from app.services.storage import FileValidationError, build_public_url, delete_file, validate_and_upload

router = APIRouter(prefix="/auth", tags=["profile"])

REQUIRED_FIELDS = {
    "full_name", "phone_number", "contact_address", "state",
    "nationality", "category", "latitude", "longitude",
    "radius_km", "working_experience",
}


@router.get("/profile", response_model=ProfileDetailResponse)
async def get_own_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(select(SolverProfile).where(SolverProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()

    kyc_result = await db.execute(select(KYCDocument).where(KYCDocument.user_id == current_user.id))
    kyc = kyc_result.scalar_one_or_none()

    solver_detail = None
    if profile:
        solver_detail = ProfileSolverDetail(
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

    kyc_detail = None
    if kyc:
        kyc_detail = ProfileKYCDetail(
            review_status=kyc.review_status,
            rejection_reason=kyc.rejection_reason,
        )

    return ProfileDetailResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        phone_number=current_user.phone_number,
        account_status=current_user.account_status,
        solver_profile=solver_detail,
        kyc_status=kyc_detail,
    )


@router.patch("/profile", response_model=ProfileUpdateResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_not_suspended(current_user)

    result = await db.execute(select(SolverProfile).where(SolverProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

    for field, value in update_data.items():
        if value is None and field in REQUIRED_FIELDS:
            raise HTTPException(status_code=400, detail=f"{field} is required and cannot be cleared")

    user_fields = {"full_name", "phone_number"}
    for field, value in update_data.items():
        if field in user_fields:
            setattr(current_user, field, value)
        else:
            setattr(profile, field, value)

    kyc_result = await db.execute(select(KYCDocument).where(KYCDocument.user_id == current_user.id))
    kyc = kyc_result.scalar_one_or_none()
    if kyc and kyc.review_status == KYCReviewStatus.REJECTED:
        kyc.review_status = KYCReviewStatus.PENDING
        kyc.reviewed_by = None
        kyc.reviewed_at = None
        kyc.rejection_reason = None

    current_user.account_status = AccountStatus.PENDING_REVIEW

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already in use")

    return ProfileUpdateResponse(detail="Profile updated. Pending re-review.", account_status=current_user.account_status)


@router.patch("/profile/files", response_model=ProfileUpdateResponse)
async def update_profile_files(
    profile_image: UploadFile | None = File(None),
    id_document: UploadFile | None = File(None),
    selfie: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_not_suspended(current_user)

    if not any([profile_image, id_document, selfie]):
        raise HTTPException(status_code=400, detail="At least one file must be provided")

    profile_result = await db.execute(select(SolverProfile).where(SolverProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    kyc_result = await db.execute(select(KYCDocument).where(KYCDocument.user_id == current_user.id))
    kyc = kyc_result.scalar_one_or_none()
    if not kyc:
        raise HTTPException(status_code=404, detail="KYC record not found")

    old_keys = []

    try:
        if profile_image:
            old_keys.append(profile.profile_image_key)
            profile.profile_image_key = await validate_and_upload(str(current_user.id), "profile_image", profile_image)
        if id_document:
            old_keys.append(kyc.id_document_key)
            kyc.id_document_key = await validate_and_upload(str(current_user.id), "id_document", id_document)
        if selfie:
            old_keys.append(kyc.selfie_key)
            kyc.selfie_key = await validate_and_upload(str(current_user.id), "selfie", selfie)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if id_document or selfie:
        kyc.review_status = KYCReviewStatus.PENDING
        kyc.reviewed_by = None
        kyc.reviewed_at = None
        kyc.rejection_reason = None

    current_user.account_status = AccountStatus.PENDING_REVIEW

    await db.commit()

    for key in old_keys:
        delete_file(key)

    return ProfileUpdateResponse(detail="Files updated. Pending re-review.", account_status=current_user.account_status)