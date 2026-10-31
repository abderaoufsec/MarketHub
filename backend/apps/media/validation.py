"""Upload validation: the part that must not trust the client.

The filename extension and the browser-supplied ``Content-Type`` are
attacker-controlled; the magic bytes are not. Everything the pipeline
accepts is decided here, against those bytes.
"""

from __future__ import annotations

#: Formats the processing pipeline can decode with Pillow *and* that are
#: safe to decode (no SVG — scriptable — and no PDF/TIFF bombs). Every one
#: is re-encoded before storage, so the bytes users download are ours.
ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

#: Human-readable list for the 400 details.
ALLOWED_LABELS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WebP",
    "image/gif": "GIF",
}


def sniff_mime(head: bytes) -> str | None:
    """The real type, from the first bytes of the file.

    ``None`` means "not a format we accept" — the caller turns that into an
    ``unsupported_image`` error rather than trying to decode it.
    """
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None
