"""Turn uploaded files and email attachments into Claude content blocks.

Files go to the Anthropic Files API once and conversations keep only the file id, so a few
PDFs can't push every later request past the API's request-size limit.
"""

import base64
import logging
from datetime import timedelta

import anthropic

from .db import Database

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # the API's per-image limit
MAX_TEXT_CHARS = 200_000  # roughly 50k tokens
TEXT_TYPES = {"application/json", "application/xml", "application/csv"}
# Files Claude can't read in a message but the code workbench can open with Python.
WORKBENCH_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
}

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
        return {"type": "document", "source": source, "title": filename, "citations": {"enabled": True}}
    if mime_type.startswith("text/") or mime_type in TEXT_TYPES:
        text = data.decode("utf-8", errors="replace")
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + f"\n[... truncated, {len(text)} characters total]"
        return {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text},
                "title": filename, "citations": {"enabled": True}}
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


ORPHAN_UPLOAD_AGE = timedelta(days=1)


class FileUploader:
    def __init__(self, client: anthropic.AsyncAnthropic, db: Database):
        self.client = client
        self.db = db

    async def to_block(self, data: bytes, mime_type: str, filename: str) -> dict:
        """Validate, upload, and return a block that references the file by id.

        Falls back to the inline block when the upload fails, so a Files API hiccup never
        loses the owner's file.
        """
        block = to_content_block(data, mime_type, filename)  # raises UnsupportedFile
        source = block["source"]
        if source["type"] == "text":
            # Possibly truncated text. A .txt name keeps it stored as text/plain, the only text
            # type document blocks accept, whatever the original extension (.csv, .json, ...).
            name = filename if filename.lower().endswith(".txt") else f"{filename}.txt"
            upload = (name, source["data"].encode("utf-8"), "text/plain")
        else:
            upload = (filename, data, source["media_type"])
        try:
            uploaded = await self.client.files.upload(file=upload)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            log.error("This API key can't use the Files API (%s); sending files inline instead", e)
            return block
        except anthropic.APIError as e:
            log.warning("Files API upload of %s failed (%s); sending it inline", filename, e)
            return block
        self.db.record_upload(uploaded.id)
        return {**block, "source": {"type": "file", "file_id": uploaded.id}}

    async def store_raw(self, data: bytes, mime_type: str, filename: str) -> str:
        """Upload a file only the code workbench can open (Excel, Word, PowerPoint); return its id."""
        if len(data) > MAX_FILE_BYTES:
            raise UnsupportedFile(f"{filename} is {_megabytes(len(data))} MB; the limit is "
                                  f"{_megabytes(MAX_FILE_BYTES)} MB.")
        uploaded = await self.client.files.upload(file=(filename, data, mime_type))
        self.db.record_upload(uploaded.id)  # not in any message, so cleanup removes it after a day
        return uploaded.id


def is_workbench_file(mime_type: str) -> bool:
    return (mime_type or "").split(";")[0].strip().lower() in WORKBENCH_TYPES


def file_ids_in(content: list[dict]) -> list[str]:
    """File ids referenced by content blocks, including inside tool results."""
    ids = []
    for block in content if isinstance(content, list) else []:
        source = block.get("source") or {}
        if source.get("type") == "file":
            ids.append(source["file_id"])
        if block.get("type") == "tool_result":
            ids += file_ids_in(block.get("content"))
    return ids


async def clean_up_uploads(client: anthropic.AsyncAnthropic, db: Database) -> int:
    """Delete uploads from finished conversations (never the current one). Returns how many."""
    deleted = 0
    for file_id in db.stale_uploads(ORPHAN_UPLOAD_AGE):
        try:
            await client.files.delete(file_id)
        except anthropic.NotFoundError:
            pass  # already gone
        except anthropic.APIError as e:
            log.warning("Couldn't delete uploaded file %s (%s); will retry", file_id, e)
            continue
        db.forget_upload(file_id)
        deleted += 1
    return deleted
