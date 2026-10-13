import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.post import MediaProcessingStatus, PostMediaType
from app.models.reaction import ReactionType


class PostAuthor(BaseModel):
    id: uuid.UUID
    full_name: str | None
    profile_image_url: str | None


class PostMediaItem(BaseModel):
    id: uuid.UUID
    media_type: PostMediaType
    position: int
    processing_status: MediaProcessingStatus
    url: str | None
    thumbnail_url: str | None


class PostCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1)
    price_tag: str | None = Field(default=None, max_length=100)
    goods_colour: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=50)
    quantity_available: int | None = Field(default=None, ge=0)


class PostUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    price_tag: str | None = Field(default=None, max_length=100)
    goods_colour: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=50)
    quantity_available: int | None = Field(default=None, ge=0)


class PostListItem(BaseModel):
    id: uuid.UUID
    author: PostAuthor
    title: str
    description: str
    price_tag: str | None
    goods_colour: str | None
    category: str | None
    condition: str | None
    quantity_available: int | None
    comment_count: int
    reaction_count: int
    my_reaction: ReactionType | None
    media: list[PostMediaItem]
    created_at: datetime
    updated_at: datetime


class PostDetail(PostListItem):
    reaction_breakdown: dict[str, int]


class PostListResponse(BaseModel):
    total: int
    page: int
    limit: int
    posts: list[PostListItem]


class PostActionResponse(BaseModel):
    detail: str
