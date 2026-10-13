from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.post import Post, PostMedia
from app.services.storage import delete_file


async def delete_post_and_media(db: AsyncSession, post: Post) -> None:
    """Hard-deletes a post and every object it owns in S3 (image/video/thumbnail, raw and
    processed). Used by both the owner's self-service delete and the admin moderation delete —
    both must leave zero trace in the bucket, not just the DB.
    """
    media_result = await db.execute(select(PostMedia).where(PostMedia.post_id == post.id))
    media_rows = media_result.scalars().all()

    keys_to_delete: list[str] = []
    for m in media_rows:
        keys_to_delete.append(m.raw_key)
        if m.processed_key and m.processed_key != m.raw_key:
            keys_to_delete.append(m.processed_key)
        if m.thumbnail_key:
            keys_to_delete.append(m.thumbnail_key)

    await db.delete(post)
    await db.commit()

    for key in keys_to_delete:
        delete_file(key)
