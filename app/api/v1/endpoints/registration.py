import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.csrf import verify_csrf
from app.db.session import get_db
from app.models.kyc_document import KYCDocument
from app.models.solver_profile import SolverProfile
from app.models.user import AccountStatus, User
from app.schemas.registration import CompleteRegistrationResponse
from app.services.storage import FileValidationError, validate_and_upload

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/complete-registration", response_model=CompleteRegistrationResponse, dependencies=[Depends(verify_csrf)])
async def complete_registration(
    phone_number: str = Form(...),
    contact_address: str = Form(...),
    state: str = Form(...),
    nationality: str = Form(...),
    category: str = Form(...),
    working_experience: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    radius_km: int = Form(...),
    shop_address: str | None = Form(None),
    description: str | None = Form(None),
    skills: str | None = Form(None),
    availability: str | None = Form(None),
    pricing_guidance: str | None = Form(None),
    response_time: str | None = Form(None),
    bank_name: str | None = Form(None),
    acct_num: str | None = Form(None),
    acct_name: str | None = Form(None),
    profile_image: UploadFile = File(...),
    id_document: UploadFile = File(...),
    selfie: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.account_status != AccountStatus.PROFILE_INCOMPLETE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration already completed")

    parsed_skills = None
    if skills:
        try:
            parsed_skills = json.loads(skills)
            if not isinstance(parsed_skills, list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="skills must be a JSON array of strings")

    try:
        profile_image_key = await validate_and_upload(str(current_user.id), "profile_image", profile_image)
        id_document_key = await validate_and_upload(str(current_user.id), "id_document", id_document)
        selfie_key = await validate_and_upload(str(current_user.id), "selfie", selfie)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    current_user.phone_number = phone_number

    profile = SolverProfile(
        user_id=current_user.id,
        profile_image_key=profile_image_key,
        contact_address=contact_address,
        shop_address=shop_address,
        state=state,
        nationality=nationality,
        category=category,
        description=description,
        skills=parsed_skills,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        working_experience=working_experience,
        availability=availability,
        pricing_guidance=pricing_guidance,
        response_time=response_time,
        bank_name=bank_name,
        acct_num=acct_num,
        acct_name=acct_name,
    )
    db.add(profile)

    kyc = KYCDocument(
        user_id=current_user.id,
        id_document_key=id_document_key,
        selfie_key=selfie_key,
    )
    db.add(kyc)

    current_user.account_status = AccountStatus.PENDING_REVIEW

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already in use")

    return CompleteRegistrationResponse(
        id=current_user.id,
        account_status=current_user.account_status,
        message="Registration submitted. Your account is pending review.",
    )