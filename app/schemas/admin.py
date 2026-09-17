import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.kyc_document import KYCReviewStatus
from app.models.user import AccountStatus, UserRole


class SolverProfileDetail(BaseModel):
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


class KYCDocumentDetail(BaseModel):
    id_document_url: str
    selfie_url: str
    review_status: KYCReviewStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None


class AdminUserDetailResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    phone_number: str | None
    role: UserRole
    account_status: AccountStatus
    created_at: datetime
    solver_profile: SolverProfileDetail | None
    kyc_document: KYCDocumentDetail | None

    model_config = {"from_attributes": True}


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewRequest(BaseModel):
    action: ReviewAction
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def reason_required_on_reject(self):
        if self.action == ReviewAction.REJECT and not self.rejection_reason:
            raise ValueError("rejection_reason is required when rejecting")
        return self


class ReviewResponse(BaseModel):
    id: uuid.UUID
    account_status: AccountStatus
    message: str


class CreateAdminRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class CreateAdminResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    account_status: AccountStatus
    message: str


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class SolverListItem(BaseModel):
    id: uuid.UUID
    full_name: str | None
    email: EmailStr
    phone_number: str | None
    category: str | None
    state: str | None
    account_status: AccountStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class SolverListResponse(BaseModel):
    total: int
    page: int
    limit: int
    solvers: list[SolverListItem]