import os
import hashlib
import threading
from pathlib import Path
from llama_parse import LlamaParse
from loguru import logger
from src.config import settings

_PARSE_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "parsed"
_PARSE_LOCKS: dict[str, threading.Lock] = {}
_PARSE_LOCKS_GUARD = threading.Lock()


def _get_parse_lock(checksum: str) -> threading.Lock:
    with _PARSE_LOCKS_GUARD:
        return _PARSE_LOCKS.setdefault(checksum, threading.Lock())


def parse_file(file_path: str) -> str:
    """
    Parses a file (PDF, image, docx, etc.) using LlamaParse and returns the extracted markdown text.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Upload not found: {file_path}")

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    _PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _PARSE_CACHE_DIR / f"{checksum}.md"

    if cache_path.exists():
        logger.info(f"Using cached LlamaParse result for: {file_path}")
        return cache_path.read_text(encoding="utf-8")

    logger.info(f"Parsing file using LlamaParse: {file_path}")
    if not settings.llama_cloud_api_key:
        raise ValueError("LLAMA_CLOUD_API_KEY is not configured in environment variables.")

    with _get_parse_lock(checksum):
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        parser = LlamaParse(
            api_key=settings.llama_cloud_api_key,
            result_type="markdown",
            verbose=True,
        )
        documents = parser.load_data(str(path))
        full_text = "\n\n".join(doc.text for doc in documents).strip()
        if not full_text:
            raise ValueError(f"LlamaParse returned no text for: {path.name}")

        temporary = cache_path.with_suffix(".part")
        temporary.write_text(full_text, encoding="utf-8")
        temporary.replace(cache_path)
        logger.info(f"Successfully parsed {len(documents)} pages/chunks from {file_path}")
        return full_text
