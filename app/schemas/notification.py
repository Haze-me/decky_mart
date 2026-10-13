import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.notification import NotificationType
from app.models.user import UserRole


class NotificationItem(BaseModel):
    id: uuid.UUID
    actor_type: UserRole
    actor_id: uuid.UUID
    notification_type: NotificationType
    post_id: uuid.UUID
    comment_id: uuid.UUID | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    total: int
    unread_count: int
    page: int
    limit: int
    notifications: list[NotificationItem]


class NotificationActionResponse(BaseModel):
    detail: str
