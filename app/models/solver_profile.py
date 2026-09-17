import uuid
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Float, Integer, ForeignKey, DateTime, func

from app.db.base import Base


class SolverProfile(Base):
    __tablename__ = "solver_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    profile_image_key: Mapped[str] = mapped_column(String(512), nullable=False)
    contact_address: Mapped[str] = mapped_column(String(500), nullable=False)
    shop_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    nationality: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_km: Mapped[int] = mapped_column(Integer, nullable=False)
    working_experience: Mapped[str] = mapped_column(String(255), nullable=False)
    availability: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pricing_guidance: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_time: Mapped[str | None] = mapped_column(String(100), nullable=True)

    bank_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    acct_num: Mapped[str | None] = mapped_column(String(20), nullable=True)
    acct_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )