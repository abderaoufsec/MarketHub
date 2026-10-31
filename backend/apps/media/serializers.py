from __future__ import annotations

from rest_framework import serializers

from .models import Image


class ImageSerializer(serializers.ModelSerializer):
    """One upload as clients consume it: absolute URLs + what the UI needs.

    ``url`` is the widest variant (detail pages); ``thumb_url``/``card_url``
    are the list sizes. ``lqip`` is an inline data URI for blur-up while the
    real file loads — a listing grid stays readable on a 2G connection.
    """

    url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()
    card_url = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    class Meta:
        model = Image
        fields = [
            "id",
            "url",
            "thumb_url",
            "card_url",
            "detail_url",
            "width",
            "height",
            "mime_type",
            "size_bytes",
            "lqip",
            "dominant_color",
            "phash",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    def _absolute(self, obj: Image, variant: str) -> str | None:
        return obj.url_for(variant, request=self.context.get("request"))

    def get_url(self, obj) -> str | None:
        return self._absolute(obj, "full")

    def get_thumb_url(self, obj) -> str | None:
        return self._absolute(obj, "thumb")

    def get_card_url(self, obj) -> str | None:
        return self._absolute(obj, "card")

    def get_detail_url(self, obj) -> str | None:
        return self._absolute(obj, "detail")


class ImageUploadSerializer(serializers.Serializer):
    """Multipart body of ``POST /media/images/``."""

    file = serializers.FileField(
        help_text="JPEG, PNG, WebP or GIF. Validated from the bytes, not the name."
    )


class PresignSerializer(serializers.Serializer):
    """What the client is about to upload, so the bucket policy can bound it."""

    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100, default="image/jpeg")
    size = serializers.IntegerField(min_value=1)

    def validate_content_type(self, value: str) -> str:
        # The bucket policy only allows ``image/*``; failing here says so in
        # the API's own envelope instead of a raw S3 403 after the upload.
        if not value.startswith("image/"):
            raise serializers.ValidationError(
                "Unsupported image format. Use JPEG, PNG, WebP or GIF."
            )
        return value

    def validate_size(self, value: int) -> int:
        from django.conf import settings

        if value > settings.MEDIA_MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("That image is too large.")
        return value


class ImportSerializer(serializers.Serializer):
    """The object key returned by a presigned POST."""

    key = serializers.CharField(max_length=512)
    original_name = serializers.CharField(max_length=255, required=False, default="")
