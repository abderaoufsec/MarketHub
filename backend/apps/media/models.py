"""One row per accepted upload.

The bytes live in storage (local disk, or S3-compatible via settings); the
row carries everything the API and the duplicate detectors need without
touching a file: dimensions, checksum, perceptual hash, LQIP and the
variant paths.
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models


class Image(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending upload"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="media_images",
    )
    #: The normalized, EXIF-free JPEG the pipeline wrote (never the upload).
    file = models.ImageField(upload_to="listings/", max_length=255)
    original_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=64, default="image/jpeg")
    size_bytes = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    #: SHA-256 of the uploaded bytes: re-uploading the same file is a retry,
    #: not a second copy (the upload view replays the existing row).
    checksum = models.CharField(max_length=64, blank=True, default="", db_index=True)
    #: 64-bit perceptual hash, hex — see apps.media.phash.
    phash = models.CharField(max_length=16, blank=True, default="", db_index=True)
    dominant_color = models.CharField(max_length=7, blank=True, default="")
    #: Inline blur-up placeholder (a ~24px WebP data URI).
    lqip = models.TextField(blank=True, default="")
    #: variant name -> storage path (thumb/card/detail/full).
    variants = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.READY)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_images"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="media_owner_created_idx"),
        ]

    def __str__(self):
        return self.original_name or f"Image {self.pk}"

    def path_for(self, variant: str) -> str | None:
        """Storage path for ``variant``, falling back to the source."""
        return self.variants.get(variant) or (self.file.name if self.file else None)

    def url_for(self, variant: str = "full", request=None) -> str | None:
        """Public URL for ``variant``; absolute when a request is given."""
        path = self.path_for(variant)
        if not path:
            return None
        url = default_storage.url(path)
        if request is not None and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    @property
    def url(self) -> str | None:
        return self.url_for("full")

    @property
    def is_attached(self) -> bool:
        """Whether a listing currently references this upload."""
        return self.product_images.exists()
