import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_not_suspended, get_active_solver, get_current_user, get_optional_actor
from app.core.actors import Actor
from app.core.config import settings
from app.core.csrf import verify_csrf
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.post import MediaProcessingStatus, Post, PostMedia, PostMediaType
from app.models.reaction import Reaction
from app.models.solver_profile import SolverProfile
from app.models.user import User, UserRole
from app.schemas.post import (
    PostActionResponse,
    PostAuthor,
    PostCreateRequest,
    PostDetail,
    PostListItem,
    PostListResponse,
    PostMediaItem,
    PostUpdateRequest,
)
from app.services.post_service import delete_post_and_media
from app.services.storage import FileValidationError, build_public_url, delete_file, validate_and_upload_post_media

router = APIRouter(prefix="/posts", tags=["posts"])


def _media_item(media: PostMedia) -> PostMediaItem:
    url = None
    if media.processing_status == MediaProcessingStatus.READY and media.processed_key:
        url = build_public_url(media.processed_key)
    thumbnail_url = build_public_url(media.thumbnail_key) if media.thumbnail_key else None
    return PostMediaItem(
        id=media.id,
        media_type=media.media_type,
        position=media.position,
        processing_status=media.processing_status,
        url=url,
        thumbnail_url=thumbnail_url,
    )


async def _authors_by_id(db: AsyncSession, author_ids: set[uuid.UUID]) -> dict[uuid.UUID, PostAuthor]:
    if not author_ids:
        return {}

    result = await db.execute(select(User).where(User.id.in_(author_ids)))
    users = {u.id: u for u in result.scalars().all()}

    profile_result = await db.execute(select(SolverProfile).where(SolverProfile.user_id.in_(author_ids)))
    profiles = {p.user_id: p for p in profile_result.scalars().all()}

    authors = {}
    for uid, user in users.items():
        profile = profiles.get(uid)
        authors[uid] = PostAuthor(
            id=user.id,
            full_name=user.full_name,
            profile_image_url=build_public_url(profile.profile_image_key) if profile else None,
        )
    return authors


async def _media_by_post(db: AsyncSession, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[PostMedia]]:
    if not post_ids:
        return {}
    result = await db.execute(select(PostMedia).where(PostMedia.post_id.in_(post_ids)).order_by(PostMedia.position))
    grouped: dict[uuid.UUID, list[PostMedia]] = {}
    for media in result.scalars().all():
        grouped.setdefault(media.post_id, []).append(media)
    return grouped


async def _my_reactions(db: AsyncSession, actor: Actor | None, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not actor or not post_ids:
        return {}
    result = await db.execute(
        select(Reaction.post_id, Reaction.reaction_type).where(
            Reaction.post_id.in_(post_ids),
            Reaction.actor_type == actor.actor_type,
            Reaction.actor_id == actor.actor_id,
        )
    )
    return {row.post_id: row.reaction_type for row in result.all()}


async def _load_owned_post(db: AsyncSession, post_id: uuid.UUID, user: User) -> Post:
    if user.role != UserRole.SOLVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the post's author can do this")

    result = await db.execute(select(Post).where(Post.id == post_id, Post.author_id == user.id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.post("", response_model=PostDetail, status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_csrf)])
@limiter.limit("10/hour")
async def create_post(
    request: Request,
    response: Response,
    title: str = Form(...),
    description: str = Form(...),
    price_tag: str | None = Form(None),
    goods_colour: str | None = Form(None),
    category: str | None = Form(None),
    condition: str | None = Form(None),
    quantity_available: int | None = Form(None),
    media: list[UploadFile] = File(...),
    current_user: User = Depends(get_active_solver),
    db: AsyncSession = Depends(get_db),
):
    payload = PostCreateRequest(
        title=title,
        description=description,
        price_tag=price_tag,
        goods_colour=goods_colour,
        category=category,
        condition=condition,
        quantity_available=quantity_available,
    )

    if not media or len(media) < 1:
        raise HTTPException(status_code=400, detail="At least one image or video is required")
    if len(media) > settings.MAX_POST_MEDIA_ITEMS:
        raise HTTPException(status_code=400, detail=f"A post can have at most {settings.MAX_POST_MEDIA_ITEMS} media items")

    post = Post(
        author_id=current_user.id,
        title=payload.title,
        description=payload.description,
        price_tag=payload.price_tag,
        goods_colour=payload.goods_colour,
        category=payload.category,
        condition=payload.condition,
        quantity_available=payload.quantity_available,
    )
    db.add(post)
    await db.flush()

    uploaded_keys: list[str] = []
    try:
        for position, upload in enumerate(media):
            media_type, key = await validate_and_upload_post_media(str(current_user.id), upload)
            uploaded_keys.append(key)
            is_image = media_type == PostMediaType.IMAGE
            db.add(
                PostMedia(
                    post_id=post.id,
                    media_type=media_type,
                    position=position,
                    raw_key=key,
                    processed_key=key if is_image else None,
                    processing_status=MediaProcessingStatus.READY if is_image else MediaProcessingStatus.PENDING,
                )
            )
    except FileValidationError as exc:
        await db.rollback()
        for key in uploaded_keys:
            delete_file(key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await db.commit()
    await db.refresh(post)

    media_rows = (await db.execute(select(PostMedia).where(PostMedia.post_id == post.id).order_by(PostMedia.position))).scalars().all()
    authors = await _authors_by_id(db, {current_user.id})
    author = authors.get(current_user.id, PostAuthor(id=current_user.id, full_name=current_user.full_name, profile_image_url=None))

    return PostDetail(
        id=post.id,
        author=author,
        title=post.title,
        description=post.description,
        price_tag=post.price_tag,
        goods_colour=post.goods_colour,
        category=post.category,
        condition=post.condition,
        quantity_available=post.quantity_available,
        comment_count=post.comment_count,
        reaction_count=post.reaction_count,
        my_reaction=None,
        media=[_media_item(m) for m in media_rows],
        created_at=post.created_at,
        updated_at=post.updated_at,
        reaction_breakdown={},
    )


@router.get("", response_model=PostListResponse)
async def list_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    actor: Actor | None = Depends(get_optional_actor),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(Post))).scalar_one()

    offset = (page - 1) * limit
    result = await db.execute(select(Post).order_by(Post.created_at.desc()).offset(offset).limit(limit))
    posts = result.scalars().all()

    post_ids = [p.id for p in posts]
    author_ids = {p.author_id for p in posts}

    authors = await _authors_by_id(db, author_ids)
    media_by_post = await _media_by_post(db, post_ids)
    my_reactions = await _my_reactions(db, actor, post_ids)

    items = [
        PostListItem(
            id=p.id,
            author=authors.get(p.author_id, PostAuthor(id=p.author_id, full_name=None, profile_image_url=None)),
            title=p.title,
            description=p.description,
            price_tag=p.price_tag,
            goods_colour=p.goods_colour,
            category=p.category,
            condition=p.condition,
            quantity_available=p.quantity_available,
            comment_count=p.comment_count,
            reaction_count=p.reaction_count,
            my_reaction=my_reactions.get(p.id),
            media=[_media_item(m) for m in media_by_post.get(p.id, [])],
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in posts
    ]

    return PostListResponse(total=total, page=page, limit=limit, posts=items)


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(
    post_id: uuid.UUID,
    actor: Actor | None = Depends(get_optional_actor),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    authors = await _authors_by_id(db, {post.author_id})
    media_by_post = await _media_by_post(db, [post.id])
    my_reactions = await _my_reactions(db, actor, [post.id])

    breakdown_result = await db.execute(
        select(Reaction.reaction_type, func.count()).where(Reaction.post_id == post.id).group_by(Reaction.reaction_type)
    )
    reaction_breakdown = {row[0].value: row[1] for row in breakdown_result.all()}

    return PostDetail(
        id=post.id,
        author=authors.get(post.author_id, PostAuthor(id=post.author_id, full_name=None, profile_image_url=None)),
        title=post.title,
        description=post.description,
        price_tag=post.price_tag,
        goods_colour=post.goods_colour,
        category=post.category,
        condition=post.condition,
        quantity_available=post.quantity_available,
        comment_count=post.comment_count,
        reaction_count=post.reaction_count,
        my_reaction=my_reactions.get(post.id),
        media=[_media_item(m) for m in media_by_post.get(post.id, [])],
        created_at=post.created_at,
        updated_at=post.updated_at,
        reaction_breakdown=reaction_breakdown,
    )


@router.patch("/{post_id}", response_model=PostActionResponse, dependencies=[Depends(verify_csrf)])
async def update_post(
    post_id: uuid.UUID,
    payload: PostUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_not_suspended(current_user)
    post = await _load_owned_post(db, post_id, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()

    return PostActionResponse(detail="Post updated")


@router.delete("/{post_id}", response_model=PostActionResponse, dependencies=[Depends(verify_csrf)])
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_not_suspended(current_user)
    post = await _load_owned_post(db, post_id, current_user)

    await delete_post_and_media(db, post)

    return PostActionResponse(detail="Post deleted")
