import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actors import Actor
from app.models.notification import Notification, NotificationType
from app.models.user import UserRole


async def notify_post_author(
    db: AsyncSession,
    *,
    actor: Actor,
    recipient_id: uuid.UUID,
    notification_type: NotificationType,
    post_id: uuid.UUID,
    comment_id: uuid.UUID | None = None,
) -> None:
    """Queues an in-app notification for a post's author. No-op if the actor is notifying
    themselves (commenting/reacting on their own post).
    """
    if actor.actor_type == UserRole.SOLVER and actor.actor_id == recipient_id:
        return

    db.add(
        Notification(
            recipient_id=recipient_id,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            notification_type=notification_type,
            post_id=post_id,
            comment_id=comment_id,
        )
    )
