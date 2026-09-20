import uuid

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.user import AccountStatus, UserRole


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResendVerificationResponse(BaseModel):
    detail: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    account_status: AccountStatus
    message: str


class RefreshResponse(BaseModel):
    detail: str


class LogoutResponse(BaseModel):
    detail: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    detail: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("new_password and confirm_password do not match")
        return self


class ResetPasswordResponse(BaseModel):
    detail: str
    
class GoogleAuthRequest(BaseModel):
    id_token: str