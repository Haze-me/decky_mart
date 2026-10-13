import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import UserRole


class CommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_comment_id: uuid.UUID | None = None


class CommentUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentAuthor(BaseModel):
    actor_type: UserRole
    actor_id: uuid.UUID
    display_name: str | None
    avatar_url: str | None = None


class CommentItem(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    parent_comment_id: uuid.UUID | None
    author: CommentAuthor
    body: str | None
    is_deleted: bool
    is_mine: bool
    created_at: datetime
    updated_at: datetime


class CommentListResponse(BaseModel):
    total: int
    page: int
    limit: int
    comments: list[CommentItem]


class CommentActionResponse(BaseModel):
    detail: str
