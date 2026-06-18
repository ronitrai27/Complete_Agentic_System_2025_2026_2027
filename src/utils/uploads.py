"""Safe upload validation and deterministic local storage."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".md"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "data" / "uploads"


@dataclass(frozen=True)
class StoredUpload:
    path: str
    original_name: str
    safe_name: str
    document_id: str
    checksum: str
    size_bytes: int
    created: bool


def sanitize_filename(filename: str) -> str:
    """Return a display-safe basename without path traversal characters."""
    basename = Path(filename or "upload").name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(basename).stem).strip("._")
    extension = Path(basename).suffix.lower()
    return f"{stem[:100] or 'upload'}{extension}"


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    if not data:
        raise ValueError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File is too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension or 'unknown'}.")

    # Reject obvious extension spoofing for binary formats. LlamaCloud performs
    # deeper parsing, while these checks cheaply stop common malformed uploads.
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("The file does not appear to be a valid PDF.")
    if extension == ".docx" and not data.startswith(b"PK"):
        raise ValueError("The file does not appear to be a valid DOCX file.")
    if extension in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("The file does not appear to be a valid JPEG image.")
    if extension == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The file does not appear to be a valid PNG image.")

    return safe_name, extension


def store_upload(filename: str, data: bytes, conversation_id: str) -> StoredUpload:
    """Validate and atomically store an upload using a content-derived ID."""
    safe_name, extension = validate_upload(filename, data)
    checksum = hashlib.sha256(data).hexdigest()
    document_id = f"doc_{checksum}"

    safe_conversation_id = re.sub(r"[^A-Za-z0-9_-]+", "_", conversation_id)[:80] or "anonymous"
    target_dir = UPLOAD_ROOT / safe_conversation_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{document_id}{extension}"

    created = not target.exists()
    if created:
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.write_bytes(data)
        temporary.replace(target)

    return StoredUpload(
        path=str(target),
        original_name=Path(filename).name,
        safe_name=safe_name,
        document_id=document_id,
        checksum=checksum,
        size_bytes=len(data),
        created=created,
    )
