"""Media endpoints (Phase 14).

* ``POST /media/images/`` — multipart upload; validated, EXIF-stripped,
  variant-built, hashed, stored. Re-uploading identical bytes replays the
  existing row (200) instead of duplicating files — a retry on a weak
  connection is not a second photo.
* ``POST /media/images/presign/`` — how to upload directly to the bucket.
* ``POST /media/images/import/`` — process an object uploaded that way.
* ``DELETE /media/images/<id>/`` — owner-only, refused while a listing uses
  it (``image_in_use``) so a published ad cannot lose its photo.
"""

from __future__ import annotations

import hashlib

from django.core.files.storage import default_storage
from django.db import transaction
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.generics import DestroyAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import ApiError

from .models import Image
from .processing import delete_files, process, read_upload
from .serializers import ImageSerializer, ImageUploadSerializer, ImportSerializer, PresignSerializer
from .storage import presign_upload


def _replay_if_known(user, raw: bytes):
    """The same bytes uploaded twice are a retry: reuse the first row."""
    checksum = hashlib.sha256(raw).hexdigest()
    existing = Image.objects.filter(
        owner=user, checksum=checksum, status=Image.Status.READY
    ).first()
    return existing


def _persist(user, raw: bytes, *, original_name: str = ""):
    processed = process(raw, original_name=original_name)
    return Image.objects.create(
        owner=user,
        file=processed.file_name,
        original_name=original_name[:255],
        mime_type=processed.mime_type,
        size_bytes=processed.size_bytes,
        width=processed.width,
        height=processed.height,
        checksum=processed.checksum,
        phash=processed.phash,
        dominant_color=processed.dominant_color,
        lqip=processed.lqip,
        variants=processed.variants,
        status=Image.Status.READY,
    )


class ImageUploadView(APIView):
    """``POST /media/images/`` — the multipart path (web, e2e, fallback)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={"multipart/form-data": ImageUploadSerializer},
        responses={201: ImageSerializer, 200: ImageSerializer},
    )
    def post(self, request):
        payload = ImageUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        upload = payload.validated_data["file"]
        raw = read_upload(upload)

        existing = _replay_if_known(request.user, raw)
        if existing is not None:
            serializer = ImageSerializer(existing, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        image = _persist(request.user, raw, original_name=getattr(upload, "name", "") or "")
        serializer = ImageSerializer(image, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PresignView(APIView):
    """``POST /media/images/presign/`` — direct-to-bucket instructions."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PresignSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        payload = PresignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        return Response(
            presign_upload(
                filename=data["filename"],
                content_type=data["content_type"],
                size=data["size"],
            )
        )


class ImportView(APIView):
    """``POST /media/images/import/`` — process an object uploaded via S3."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ImportSerializer,
        responses={201: ImageSerializer, 200: ImageSerializer},
    )
    def post(self, request):
        payload = ImportSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        key = payload.validated_data["key"].lstrip("/")
        # Only the presigned namespace is importable: nothing else in the
        # bucket is ours to reinterpret.
        if not key.startswith("uploads/"):
            raise ApiError(
                "That object key is not an upload.",
                code="image_not_found",
                status_code=404,
            )
        try:
            with default_storage.open(key, "rb") as stored:
                raw = read_upload(stored)
        except (FileNotFoundError, OSError):
            raise ApiError(
                "That upload could not be found.",
                code="image_not_found",
                status_code=404,
            ) from None

        existing = _replay_if_known(request.user, raw)
        if existing is not None:
            serializer = ImageSerializer(existing, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        image = _persist(
            request.user, raw, original_name=payload.validated_data.get("original_name", "")
        )
        serializer = ImageSerializer(image, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ImageDetailView(DestroyAPIView):
    """``DELETE /media/images/<id>/`` — owner-only, never while attached."""

    permission_classes = [IsAuthenticated]
    serializer_class = ImageSerializer

    def get_queryset(self):
        # Scoped to the caller: a stranger gets 404, not 403 (Phase 13 rule).
        return Image.objects.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        if instance.is_attached:
            raise ApiError(
                "This image is used by a listing. Remove it from the listing first.",
                code="image_in_use",
                status_code=409,
            )
        with transaction.atomic():
            delete_files(instance)
            instance.delete()
