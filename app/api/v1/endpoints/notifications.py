import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.csrf import verify_csrf
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationActionResponse, NotificationItem, NotificationListResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(Notification).where(Notification.recipient_id == current_user.id)

    total = (
        await db.execute(select(func.count()).select_from(Notification).where(Notification.recipient_id == current_user.id))
    ).scalar_one()
    unread_count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == current_user.id, Notification.is_read == False)
        )
    ).scalar_one()

    offset = (page - 1) * limit
    result = await db.execute(base.order_by(Notification.created_at.desc()).offset(offset).limit(limit))
    notifications = result.scalars().all()

    return NotificationListResponse(
        total=total,
        unread_count=unread_count,
        page=page,
        limit=limit,
        notifications=[NotificationItem.model_validate(n, from_attributes=True) for n in notifications],
    )


@router.patch("/{notification_id}/read", response_model=NotificationActionResponse, dependencies=[Depends(verify_csrf)])
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.recipient_id == current_user.id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notification.is_read = True
    await db.commit()
    return NotificationActionResponse(detail="Notification marked as read")


@router.patch("/read-all", response_model=NotificationActionResponse, dependencies=[Depends(verify_csrf)])
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.recipient_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return NotificationActionResponse(detail="All notifications marked as read")
