import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_optional_actor
from app.core.csrf import verify_csrf
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.comment import Comment
from app.models.notification import NotificationType
from app.models.post import Post
from app.models.user import User, UserRole
from app.schemas.comment import (
    CommentActionResponse,
    CommentAuthor,
    CommentCreateRequest,
    CommentItem,
    CommentListResponse,
    CommentUpdateRequest,
)
from app.services.notification_service import notify_post_author

router = APIRouter(tags=["comments"])


async def _resolve_display_names(db: AsyncSession, actors: set[tuple[UserRole, uuid.UUID]]) -> dict[tuple[UserRole, uuid.UUID], str | None]:
    local_ids = {actor_id for actor_type, actor_id in actors if actor_type in (UserRole.SOLVER, UserRole.ADMIN)}
    names: dict[tuple[UserRole, uuid.UUID], str | None] = {key: None for key in actors}
    if not local_ids:
        return names

    result = await db.execute(select(User).where(User.id.in_(local_ids)))
    users = {u.id: u.full_name for u in result.scalars().all()}
    for actor_type, actor_id in actors:
        if actor_type in (UserRole.SOLVER, UserRole.ADMIN):
            names[(actor_type, actor_id)] = users.get(actor_id)
    return names


def _comment_item(comment: Comment, live_names: dict[tuple[UserRole, uuid.UUID], str | None], actor: Actor | None) -> CommentItem:
    is_mine = bool(actor and actor.actor_type == comment.actor_type and actor.actor_id == comment.actor_id)

    if comment.actor_type == UserRole.CUSTOMER:
        # No live lookup is possible for a customer - we only ever see their profile data in the
        # token they presented at comment-creation time, so use what was snapshotted then.
        display_name = comment.actor_display_name
        avatar_url = comment.actor_avatar_url
    else:
        display_name = live_names.get((comment.actor_type, comment.actor_id))
        avatar_url = None

    return CommentItem(
        id=comment.id,
        post_id=comment.post_id,
        parent_comment_id=comment.parent_comment_id,
        author=CommentAuthor(actor_type=comment.actor_type, actor_id=comment.actor_id, display_name=display_name, avatar_url=avatar_url),
        body=None if comment.is_deleted else comment.body,
        is_deleted=comment.is_deleted,
        is_mine=is_mine,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
@limiter.limit("30/hour")
async def create_comment(
    request: Request,
    response: Response,
    post_id: uuid.UUID,
    payload: CommentCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if payload.parent_comment_id:
        parent_result = await db.execute(
            select(Comment).where(Comment.id == payload.parent_comment_id, Comment.post_id == post_id)
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent comment not found on this post")

    comment = Comment(
        post_id=post_id,
        parent_comment_id=payload.parent_comment_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        body=payload.body,
        actor_display_name=actor.display_name if actor.actor_type == UserRole.CUSTOMER else None,
        actor_avatar_url=actor.avatar_url if actor.actor_type == UserRole.CUSTOMER else None,
    )
    db.add(comment)

    await db.execute(update(Post).where(Post.id == post_id).values(comment_count=Post.comment_count + 1))

    await notify_post_author(
        db,
        actor=actor,
        recipient_id=post.author_id,
        notification_type=NotificationType.COMMENT,
        post_id=post_id,
        comment_id=None,
    )

    await db.commit()
    await db.refresh(comment)

    names = await _resolve_display_names(db, {(actor.actor_type, actor.actor_id)})
    return _comment_item(comment, names, actor)


@router.get("/posts/{post_id}/comments", response_model=CommentListResponse)
async def list_comments(
    post_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    actor: Actor | None = Depends(get_optional_actor),
    db: AsyncSession = Depends(get_db),
):
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    if not post_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    total = (await db.execute(select(func.count()).select_from(Comment).where(Comment.post_id == post_id))).scalar_one()

    offset = (page - 1) * limit
    result = await db.execute(
        select(Comment).where(Comment.post_id == post_id).order_by(Comment.created_at.asc()).offset(offset).limit(limit)
    )
    comments = result.scalars().all()

    actor_keys = {(c.actor_type, c.actor_id) for c in comments}
    names = await _resolve_display_names(db, actor_keys)

    items = [_comment_item(c, names, actor) for c in comments]

    return CommentListResponse(total=total, page=page, limit=limit, comments=items)


async def _load_own_comment(db: AsyncSession, comment_id: uuid.UUID, actor: Actor) -> Comment:
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment or comment.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.actor_type != actor.actor_type or comment.actor_id != actor.actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the comment's author can do this")
    return comment


@router.patch("/comments/{comment_id}", response_model=CommentActionResponse, dependencies=[Depends(verify_csrf)])
async def update_comment(
    comment_id: uuid.UUID,
    payload: CommentUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    comment = await _load_own_comment(db, comment_id, actor)
    comment.body = payload.body
    await db.commit()
    return CommentActionResponse(detail="Comment updated")


@router.delete("/comments/{comment_id}", response_model=CommentActionResponse, dependencies=[Depends(verify_csrf)])
async def delete_comment(
    comment_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    comment = await _load_own_comment(db, comment_id, actor)
    comment.is_deleted = True
    await db.execute(update(Post).where(Post.id == comment.post_id).values(comment_count=Post.comment_count - 1))
    await db.commit()
    return CommentActionResponse(detail="Comment deleted")
