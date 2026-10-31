"""The upload pipeline: sniff -> validate -> normalize -> variants -> hashes.

Everything is written through Django's default storage, so the same code
pours into local disk in development/tests and into an S3-compatible bucket
(MinIO/R2/S3) in production.

What the pipeline guarantees for every accepted image:

* the **real** format decided from magic bytes, never the filename;
* EXIF (including GPS) is gone — the image is re-encoded onto a fresh
  canvas, and ``exif_transpose`` has already applied the orientation, so a
  phone photo from any angle arrives upright;
* responsive WebP variants (thumb/card/detail/full) that never upscale;
* a 64-bit perceptual hash and a tiny inline LQIP placeholder;
* an optional watermark on the two largest variants;
* the result is what users download — the uploaded bytes are never served.
"""

from __future__ import annotations

import base64
import hashlib
import io
import uuid
from dataclasses import dataclass, field

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from core.exceptions import ApiError

from .phash import phash
from .validation import ALLOWED_LABELS, ALLOWED_MIME, sniff_mime

#: Read this far past the limit so "too large" is distinguishable from
#: "exactly at the limit" without buffering an unbounded stream.
_SNIFF_BYTES = 16


@dataclass
class ProcessedImage:
    """Everything the ``Image`` row needs, with files already in storage."""

    file_name: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    checksum: str
    phash: str
    dominant_color: str
    lqip: str
    variants: dict = field(default_factory=dict)


def read_upload(upload) -> bytes:
    """The raw bytes of an uploaded file, bounded by the configured limit."""
    limit = settings.MEDIA_MAX_UPLOAD_BYTES
    raw = upload.read(limit + 1)
    if len(raw) > limit:
        raise ApiError(
            "That image is too large.",
            code="image_too_large",
            status_code=413,
            details={"limit_bytes": limit},
        )
    if not raw:
        raise ApiError(
            "The uploaded file is empty.",
            code="unsupported_image",
            status_code=400,
        )
    return raw


def _open_and_validate(raw: bytes, *, original_name: str = ""):
    """Sniff, scan, decode and bound-check; the single gate for bytes."""
    mime = sniff_mime(raw[:_SNIFF_BYTES])
    if mime not in ALLOWED_MIME:
        raise ApiError(
            "Unsupported image format. Use JPEG, PNG, WebP or GIF.",
            code="unsupported_image",
            status_code=400,
            details={"allowed": sorted(ALLOWED_LABELS[m] for m in ALLOWED_MIME)},
        )
    run_scan_hook(raw, mime, original_name)

    # Pillow's decompression-bomb guard is module-global; scope it to this
    # call so one upload's settings cannot leak into another's.
    previous_limit = PILImage.MAX_IMAGE_PIXELS
    PILImage.MAX_IMAGE_PIXELS = settings.MEDIA_MAX_PIXELS
    try:
        image = PILImage.open(io.BytesIO(raw))
        # Header first: reject absurd dimensions before decoding any pixels.
        width, height = image.size
        if width * height > settings.MEDIA_MAX_PIXELS:
            raise ApiError(
                "That image has too many pixels.",
                code="image_dimensions",
                status_code=400,
                details={"max_pixels": settings.MEDIA_MAX_PIXELS},
            )
        if (
            min(width, height) < settings.MEDIA_MIN_DIMENSION
            or max(width, height) > settings.MEDIA_MAX_DIMENSION
        ):
            raise ApiError(
                "That image's dimensions are outside the allowed range.",
                code="image_dimensions",
                status_code=400,
                details={
                    "min": settings.MEDIA_MIN_DIMENSION,
                    "max": settings.MEDIA_MAX_DIMENSION,
                },
            )
        image.load()
    except ApiError:
        raise
    except PILImage.DecompressionBombError:
        # Pillow refuses anything above 2x MAX_IMAGE_PIXELS inside ``open()``;
        # without this branch an 80 MP photo would be a 500, not a 400.
        raise ApiError(
            "That image has too many pixels.",
            code="image_dimensions",
            status_code=400,
            details={"max_pixels": settings.MEDIA_MAX_PIXELS},
        ) from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ApiError(
            "That file is not a readable image.",
            code="unsupported_image",
            status_code=400,
        ) from None
    finally:
        PILImage.MAX_IMAGE_PIXELS = previous_limit
    return image, mime


def run_scan_hook(raw: bytes, mime: str, filename: str = "") -> None:
    """Give the configured malware scanner a look; reject on any verdict.

    The hook is deployment glue (ClamAV wrapper, a vendor SDK): it is
    called with the raw bytes and may raise, return ``False``, or return
    ``{"infected": True}``. A crashing scanner fails **closed** — an
    unscanned upload is worse than a rejected one.
    """
    hook_path = settings.MEDIA_SCAN_HOOK
    if not hook_path:
        return
    hook = import_string(hook_path)
    try:
        verdict = hook(raw, mime, filename)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(
            "That image could not be scanned, so it was not accepted.",
            code="upload_rejected",
            status_code=400,
        ) from exc
    if verdict is False or (isinstance(verdict, dict) and verdict.get("infected")):
        raise ApiError(
            "That image was rejected by the security scanner.",
            code="upload_rejected",
            status_code=400,
        )


def dominant_color(image: PILImage.Image) -> str:
    """The average colour as ``#rrggbb`` — the LQIP's backdrop."""
    red, green, blue = image.convert("RGB").resize((1, 1), PILImage.Resampling.BOX).getpixel((0, 0))
    return f"#{red:02x}{green:02x}{blue:02x}"


def build_lqip(image: PILImage.Image) -> str:
    """A ~24px WebP data URI: the blur-up placeholder inlined in JSON."""
    tiny = image.convert("RGB").copy()
    tiny.thumbnail((24, 24), PILImage.Resampling.LANCZOS)
    buffer = io.BytesIO()
    tiny.save(buffer, format="WEBP", quality=35, method=4)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _watermark(image: PILImage.Image) -> PILImage.Image:
    """A small translucent wordmark, bottom-right (opt-in via settings)."""
    if not settings.MEDIA_WATERMARK:
        return image
    marked = image.convert("RGB").copy()
    draw = ImageDraw.Draw(marked, "RGBA")
    size = max(14, marked.width // 32)
    font = ImageFont.load_default(size=size)
    text = "MarketHub"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad = max(8, size // 2)
    x = marked.width - (right - left) - pad
    y = marked.height - (bottom - top) - pad
    # A dark offset keeps the white mark legible on light backgrounds.
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 90))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 205))
    return marked


def _resized(image: PILImage.Image, width: int) -> PILImage.Image:
    """Downscale to ``width``; never enlarge a smaller image."""
    if image.width <= width:
        return image.copy()
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), PILImage.Resampling.LANCZOS)


def process(raw: bytes, *, original_name: str = "") -> ProcessedImage:
    """Decode, normalize, hash and store one image; return its metadata."""
    image, _mime = _open_and_validate(raw, original_name=original_name)

    # Auto-rotate (the orientation tag is applied, then dropped) and flatten
    # every mode onto RGB: no palette quirks, no alpha on JPEG.
    image = ImageOps.exif_transpose(image) or image
    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    checksum = hashlib.sha256(raw).hexdigest()
    perceived = phash(image)
    color = dominant_color(image)
    lqip = build_lqip(image)

    folder = f"listings/{uuid.uuid4().hex}"
    quality = settings.MEDIA_IMAGE_QUALITY
    variants: dict[str, str] = {}
    for name, target in settings.MEDIA_VARIANT_WIDTHS.items():
        variant = _resized(image, target)
        if name in ("detail", "full"):
            variant = _watermark(variant)
        buffer = io.BytesIO()
        variant.save(buffer, format="WEBP", quality=quality, method=6)
        variants[name] = default_storage.save(
            f"{folder}/{name}.webp", ContentFile(buffer.getvalue())
        )

    # The source is a clean JPEG bounded by the widest variant: universally
    # decodable, EXIF-free (re-encoded), and never the uploaded bytes.
    source = _resized(image, settings.MEDIA_VARIANT_WIDTHS["full"])
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", quality=88, optimize=True)
    file_name = default_storage.save(f"{folder}/source.jpg", ContentFile(buffer.getvalue()))

    return ProcessedImage(
        file_name=file_name,
        mime_type="image/jpeg",
        size_bytes=len(buffer.getvalue()),
        width=width,
        height=height,
        checksum=checksum,
        phash=perceived,
        dominant_color=color,
        lqip=lqip,
        variants=variants,
    )


def delete_files(image) -> None:
    """Best-effort removal of every object an ``Image`` row owns."""
    names = (
        [image.file.name, *image.variants.values()] if image.file else list(image.variants.values())
    )
    for name in dict.fromkeys(n for n in names if n):
        try:
            default_storage.delete(name)
        except OSError:
            # A missing object is the state we wanted anyway.
            continue
