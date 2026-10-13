import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import UserRole


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # actor_type/actor_id identify the commenter across services: SOLVER/ADMIN resolve against
    # this service's own users table, CUSTOMER resolves against the separate customer service
    # (no local FK is possible for that case, hence no DB-level FK on actor_id).
    actor_type: Mapped[UserRole] = mapped_column(ENUM(UserRole, name="user_role", create_type=False), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    # Snapshot taken at creation time, from the actor's own token/session. Only ever populated for
    # CUSTOMER actors - we have no way to look up a customer's current name/avatar later, unlike
    # solver/admin which are always resolved live against our own users table (see comments.py).
    # Null for SOLVER/ADMIN rows by design, not a missing-data bug.
    actor_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
