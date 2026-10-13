import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import UserRole


class ReactionType(str, enum.Enum):
    LIKE = "like"
    SUPPORT = "support"
    LOVE = "love"
    CURIOUS = "curious"


class Reaction(Base):
    __tablename__ = "post_reactions"
    __table_args__ = (UniqueConstraint("post_id", "actor_type", "actor_id", name="uq_post_reaction_actor"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)

    actor_type: Mapped[UserRole] = mapped_column(ENUM(UserRole, name="user_role", create_type=False), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    reaction_type: Mapped[ReactionType] = mapped_column(Enum(ReactionType, name="reaction_type"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
