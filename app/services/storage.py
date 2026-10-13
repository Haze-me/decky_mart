import uuid

import boto3
from botocore.config import Config
from fastapi import UploadFile
from app.core.config import settings
from app.models.post import PostMediaType

import logging
logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    config=Config(signature_version="s3v4"),
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

FILE_TYPE_CONFIG = {
    "profile_image": {"max_size_mb": settings.MAX_PROFILE_IMAGE_SIZE_MB, "prefix": "profile-images"},
    "id_document": {"max_size_mb": settings.MAX_ID_DOCUMENT_SIZE_MB, "prefix": "id-documents"},
    "selfie": {"max_size_mb": settings.MAX_SELFIE_SIZE_MB, "prefix": "selfies"},
}


class FileValidationError(Exception):
    pass


def _build_object_key(user_id: str, file_type: str, content_type: str) -> str:
    ext = "jpg" if content_type == "image/jpeg" else "png"
    prefix = FILE_TYPE_CONFIG[file_type]["prefix"]
    return f"solver-registration/{user_id}/{prefix}/{uuid.uuid4()}.{ext}"


async def validate_and_upload(user_id: str, file_type: str, upload: UploadFile) -> str:
    if file_type not in FILE_TYPE_CONFIG:
        raise FileValidationError(f"Invalid file_type: {file_type}")

    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise FileValidationError(f"{file_type}: only JPG and PNG are allowed")

    contents = await upload.read()
    max_size_bytes = FILE_TYPE_CONFIG[file_type]["max_size_mb"] * 1024 * 1024

    if len(contents) > max_size_bytes:
        raise FileValidationError(
            f"{file_type}: file exceeds {FILE_TYPE_CONFIG[file_type]['max_size_mb']}MB limit"
        )

    key = _build_object_key(user_id, file_type, upload.content_type)

    s3_client.put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=key,
        Body=contents,
        ContentType=upload.content_type,
    )

    return key

POST_IMAGE_CONTENT_TYPES = {"image/jpeg": "jpg", "image/png": "png"}
POST_VIDEO_CONTENT_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov"}


async def validate_and_upload_post_media(user_id: str, upload: UploadFile) -> tuple[PostMediaType, str]:
    """Validates and uploads a single post image/video. Images are uploaded straight to the
    public post-media/images/ prefix (ready immediately).

    Video is intentionally rejected for now: there is no transcoding pipeline yet, so a video
    upload would succeed but sit at processing_status=PENDING forever with no playable URL.
    Re-enabling it is just removing this branch once MediaConvert is wired up — the private
    post-media/videos/raw/ prefix and PostMediaType.VIDEO plumbing are already in place.
    """
    if upload.content_type in POST_IMAGE_CONTENT_TYPES:
        media_type = PostMediaType.IMAGE
        ext = POST_IMAGE_CONTENT_TYPES[upload.content_type]
        max_size_bytes = settings.MAX_POST_IMAGE_SIZE_MB * 1024 * 1024
        prefix = "post-media/images"
    elif upload.content_type in POST_VIDEO_CONTENT_TYPES:
        raise FileValidationError("Video posts aren't available yet — please upload images only")
    else:
        raise FileValidationError("Only JPG/PNG images are allowed")

    contents = await upload.read()
    if len(contents) > max_size_bytes:
        limit_mb = settings.MAX_POST_IMAGE_SIZE_MB if media_type == PostMediaType.IMAGE else settings.MAX_POST_VIDEO_SIZE_MB
        raise FileValidationError(f"{media_type.value}: file exceeds {limit_mb}MB limit")

    key = f"{prefix}/{user_id}/{uuid.uuid4()}.{ext}"

    s3_client.put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=key,
        Body=contents,
        ContentType=upload.content_type,
    )

    return media_type, key


def delete_file(key: str) -> None:
    try:
        s3_client.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete S3 object %s: %s", key, exc)
        
def build_public_url(key: str) -> str:
    return f"{settings.AWS_S3_PUBLIC_BASE_URL}/{key}"


def generate_presigned_get_url(key: str, expires_in: int = 900) -> str:
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )