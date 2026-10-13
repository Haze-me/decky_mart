import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.csrf import verify_csrf
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.notification import NotificationType
from app.models.post import Post
from app.models.reaction import Reaction
from app.schemas.reaction import ReactionRequest, ReactionResponse
from app.services.notification_service import notify_post_author

router = APIRouter(prefix="/posts/{post_id}/reaction", tags=["reactions"])


async def _breakdown(db: AsyncSession, post_id: uuid.UUID) -> dict[str, int]:
    result = await db.execute(
        select(Reaction.reaction_type, func.count()).where(Reaction.post_id == post_id).group_by(Reaction.reaction_type)
    )
    return {row[0].value: row[1] for row in result.all()}


@router.put("", response_model=ReactionResponse, dependencies=[Depends(verify_csrf)])
@limiter.limit("60/minute")
async def set_reaction(
    request: Request,
    response: Response,
    post_id: uuid.UUID,
    payload: ReactionRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    existing_result = await db.execute(
        select(Reaction).where(
            Reaction.post_id == post_id,
            Reaction.actor_type == actor.actor_type,
            Reaction.actor_id == actor.actor_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.reaction_type = payload.reaction_type
        await db.commit()
    else:
        db.add(
            Reaction(
                post_id=post_id,
                actor_type=actor.actor_type,
                actor_id=actor.actor_id,
                reaction_type=payload.reaction_type,
            )
        )
        await db.execute(update(Post).where(Post.id == post_id).values(reaction_count=Post.reaction_count + 1))
        await notify_post_author(
            db,
            actor=actor,
            recipient_id=post.author_id,
            notification_type=NotificationType.REACTION,
            post_id=post_id,
        )
        try:
            await db.commit()
        except IntegrityError:
            # Lost a race with another request from the same actor; fall back to an update.
            await db.rollback()
            existing_result = await db.execute(
                select(Reaction).where(
                    Reaction.post_id == post_id,
                    Reaction.actor_type == actor.actor_type,
                    Reaction.actor_id == actor.actor_id,
                )
            )
            existing = existing_result.scalar_one()
            existing.reaction_type = payload.reaction_type
            await db.commit()

    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one()
    breakdown = await _breakdown(db, post_id)

    return ReactionResponse(my_reaction=payload.reaction_type, reaction_count=post.reaction_count, reaction_breakdown=breakdown)


@router.delete("", response_model=ReactionResponse, dependencies=[Depends(verify_csrf)])
async def remove_reaction(
    post_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    existing_result = await db.execute(
        select(Reaction).where(
            Reaction.post_id == post_id,
            Reaction.actor_type == actor.actor_type,
            Reaction.actor_id == actor.actor_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No reaction to remove")

    await db.delete(existing)
    await db.execute(update(Post).where(Post.id == post_id).values(reaction_count=Post.reaction_count - 1))
    await db.commit()

    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one()
    breakdown = await _breakdown(db, post_id)

    return ReactionResponse(my_reaction=None, reaction_count=post.reaction_count, reaction_breakdown=breakdown)
