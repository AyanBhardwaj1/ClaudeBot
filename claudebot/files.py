"""Turn uploaded files and email attachments into Claude content blocks."""

import base64

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # the API's per-image limit
MAX_TEXT_CHARS = 200_000  # roughly 50k tokens
TEXT_TYPES = {"application/json", "application/xml", "application/csv"}

# Senders choose the declared type, so check the bytes really are what they claim to be.
IMAGE_SIGNATURES = {
    "image/jpeg": lambda d: d.startswith(b"\xff\xd8\xff"),
    "image/png": lambda d: d.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/gif": lambda d: d.startswith((b"GIF87a", b"GIF89a")),
    "image/webp": lambda d: d[:4] == b"RIFF" and d[8:12] == b"WEBP",
}


class UnsupportedFile(ValueError):
    pass


def _megabytes(n: int) -> int:
    return n // (1024 * 1024)


def to_content_block(data: bytes, mime_type: str, filename: str) -> dict:
    """Return a document or image block for PDFs, text files and images."""
    if len(data) > MAX_FILE_BYTES:
        raise UnsupportedFile(
            f"{filename} is {_megabytes(len(data))} MB; the limit is {_megabytes(MAX_FILE_BYTES)} MB."
        )
    mime_type = (mime_type or "").split(";")[0].strip().lower()
    if mime_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise UnsupportedFile(f"{filename} says it's a PDF but isn't one.")
        source = {"type": "base64", "media_type": "application/pdf",
                  "data": base64.standard_b64encode(data).decode()}
        return {"type": "document", "source": source, "title": filename}
    if mime_type.startswith("text/") or mime_type in TEXT_TYPES:
        text = data.decode("utf-8", errors="replace")
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + f"\n[... truncated, {len(text)} characters total]"
        return {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text},
                "title": filename}
    if mime_type in IMAGE_SIGNATURES:
        if not IMAGE_SIGNATURES[mime_type](data):
            raise UnsupportedFile(f"{filename} says it's {mime_type} but isn't.")
        if len(data) > MAX_IMAGE_BYTES:
            raise UnsupportedFile(
                f"{filename} is {_megabytes(len(data))} MB; images can be at most "
                f"{_megabytes(MAX_IMAGE_BYTES)} MB. Send it as a photo so Telegram compresses it."
            )
        source = {"type": "base64", "media_type": mime_type, "data": base64.standard_b64encode(data).decode()}
        return {"type": "image", "source": source}
    raise UnsupportedFile(
        f"I can't read {filename} ({mime_type or 'unknown type'}). PDFs, text files and images work."
    )
