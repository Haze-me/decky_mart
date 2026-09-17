import uuid

from pydantic import BaseModel

from app.models.user import AccountStatus


class CompleteRegistrationResponse(BaseModel):
    id: uuid.UUID
    account_status: AccountStatus
    message: str