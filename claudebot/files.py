"""Turn uploaded files and email attachments into Claude content blocks."""

import base64

MAX_FILE_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
TEXT_TYPES = {"application/json", "application/xml", "application/csv"}


class UnsupportedFile(ValueError):
    pass


def to_content_block(data: bytes, mime_type: str, filename: str) -> dict:
    """Return a document or image block for PDFs, text files and images."""
    if len(data) > MAX_FILE_BYTES:
        raise UnsupportedFile(
            f"{filename} is {len(data) // (1024 * 1024)} MB; the limit is {MAX_FILE_BYTES // (1024 * 1024)} MB."
        )
    mime_type = (mime_type or "").split(";")[0].strip().lower()
    if mime_type == "application/pdf":
        source = {"type": "base64", "media_type": "application/pdf",
                  "data": base64.standard_b64encode(data).decode()}
        return {"type": "document", "source": source, "title": filename}
    if mime_type.startswith("text/") or mime_type in TEXT_TYPES:
        source = {"type": "text", "media_type": "text/plain",
                  "data": data.decode("utf-8", errors="replace")}
        return {"type": "document", "source": source, "title": filename}
    if mime_type in IMAGE_TYPES:
        source = {"type": "base64", "media_type": mime_type,
                  "data": base64.standard_b64encode(data).decode()}
        return {"type": "image", "source": source}
    raise UnsupportedFile(
        f"I can't read {filename} ({mime_type or 'unknown type'}). PDFs, text files and images work."
    )
