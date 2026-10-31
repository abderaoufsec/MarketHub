"""Direct-upload (signed URL) support.

Small images go through ``POST /media/images/`` (multipart, server-side
processing). Large ones can skip the API process: the client asks for a
**presigned POST**, uploads straight to the bucket, then asks the API to
``import`` the object by key — the same validation and processing run, but
the bytes never travel through Django.

Local storage has no presigning, so the presign endpoint answers
``mode="direct"`` with the multipart endpoint instead. Clients branch on
``mode``; nothing else differs.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.urls import NoReverseMatch, reverse


def _upload_url() -> str:
    """The multipart endpoint's path (namespaced under ``v1`` in core/urls)."""
    try:
        return reverse("v1:media-image-list")
    except NoReverseMatch:  # pragma: no cover - only if the include changes
        return reverse("media-image-list")


def storage_is_s3() -> bool:
    """Whether the configured media backend is S3-compatible."""
    return bool(settings.AWS_STORAGE_BUCKET_NAME) or "s3" in settings.MEDIA_STORAGE_BACKEND.lower()


def _safe_name(filename: str) -> str:
    name = PurePosixPath(filename or "upload").name
    return name[:120] or "upload"


def presign_upload(*, filename: str, content_type: str, size: int) -> dict:
    """Describe how the client should upload, for the current backend."""
    if not storage_is_s3():
        return {
            "mode": "direct",
            "upload_url": _upload_url(),
            "object_key": None,
            "fields": None,
        }
    return {
        "mode": "s3",
        **s3_presign(filename=filename, content_type=content_type, size=size),
    }


def s3_presign(*, filename: str, content_type: str, size: int) -> dict:
    """A presigned POST for one object (lazy boto3: deploy-time dependency)."""
    import boto3

    endpoint = settings.AWS_S3_ENDPOINT_URL or None
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.AWS_S3_REGION_NAME or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )
    key = f"uploads/{uuid.uuid4().hex}/{_safe_name(filename)}"
    post = client.generate_presigned_post(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        ExpiresIn=600,
        Conditions=[
            ["content-length-range", 1, settings.MEDIA_MAX_UPLOAD_BYTES],
            ["starts-with", "$Content-Type", "image/"],
        ],
    )
    return {
        "upload_url": post["url"],
        "object_key": key,
        "fields": post["fields"],
        "expires_in": 600,
        "max_bytes": settings.MEDIA_MAX_UPLOAD_BYTES,
        "content_type": content_type,
        "size": size,
    }
