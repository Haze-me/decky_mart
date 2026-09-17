import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Enum, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    SOLVER = "solver"
    CUSTOMER = "customer"
    ADMIN = "admin"

class AccountStatus(str, enum.Enum):
    PENDING_EMAIL_VERIFICATION = "pending_email_verification"
    EMAIL_VERIFIED = "email_verified"
    PROFILE_INCOMPLETE = "profile_incomplete"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status"),
        nullable=False,
        default=AccountStatus.PENDING_EMAIL_VERIFICATION,
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())