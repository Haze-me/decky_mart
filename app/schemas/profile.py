from pydantic import BaseModel
from app.models.kyc_document import KYCReviewStatus
from app.models.user import AccountStatus


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    contact_address: str | None = None
    shop_address: str | None = None
    state: str | None = None
    nationality: str | None = None
    category: str | None = None
    description: str | None = None
    skills: list[str] | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: int | None = None
    working_experience: str | None = None
    availability: str | None = None
    pricing_guidance: str | None = None
    response_time: str | None = None
    bank_name: str | None = None
    acct_num: str | None = None
    acct_name: str | None = None


class ProfileUpdateResponse(BaseModel):
    detail: str
    account_status: AccountStatus


class ProfileSolverDetail(BaseModel):
    profile_image_url: str
    contact_address: str
    shop_address: str | None
    state: str
    nationality: str
    category: str
    description: str | None
    skills: list[str] | None
    latitude: float
    longitude: float
    radius_km: int
    working_experience: str
    availability: str | None
    pricing_guidance: str | None
    response_time: str | None
    bank_name: str | None
    acct_num: str | None
    acct_name: str | None


class ProfileKYCDetail(BaseModel):
    review_status: KYCReviewStatus
    rejection_reason: str | None


class ProfileDetailResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    phone_number: str | None
    account_status: AccountStatus
    solver_profile: ProfileSolverDetail | None
    kyc_status: ProfileKYCDetail | None