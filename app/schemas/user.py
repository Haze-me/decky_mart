import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.user import AccountStatus, UserRole


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class RegisterResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    account_status: AccountStatus
    created_at: datetime

    model_config = {"from_attributes": True}
    
    
class UserMeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    phone_number: str | None
    role: UserRole
    account_status: AccountStatus

    model_config = {"from_attributes": True}