import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostMediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class MediaProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    price_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    goods_colour: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity_available: Mapped[int | None] = mapped_column(Integer, nullable=True)

    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PostMedia(Base):
    __tablename__ = "post_media"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)

    media_type: Mapped[PostMediaType] = mapped_column(Enum(PostMediaType, name="post_media_type"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Original uploaded object (private for video until processed; images are uploaded straight to the public key).
    raw_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # Public, playable/viewable object key. Set immediately for images; set once MediaConvert finishes for video.
    processed_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    processing_status: Mapped[MediaProcessingStatus] = mapped_column(
        Enum(MediaProcessingStatus, name="media_processing_status"),
        nullable=False,
        default=MediaProcessingStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
