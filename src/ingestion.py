"""Lane 1 mock ingestion. Real PDF, image, and OCR extraction replaces this."""

import re
import uuid
from pathlib import Path

from src.contracts import IngestionResult, PageText

_CODE_SUFFIXES = {".py", ".js", ".ts", ".java", ".go", ".sh", ".env", ".yml", ".yaml", ".json"}


def _language(text: str) -> str:
    has_arabic = bool(re.search(r"[؀-ۿ]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    return "en" if has_latin else "unknown"


def ingest(text: str | None = None, file_path: str | None = None) -> IngestionResult:
    """Normalize pasted text or a UTF-8 file. Raises ValueError when nothing is readable."""
    filename = None
    input_type = "text"
    if file_path:
        path = Path(file_path)
        filename = path.name
        input_type = "code" if path.suffix.lower() in _CODE_SUFFIXES else "text"
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # shortcut: binary files are rejected, replace when real PDF and OCR extraction lands
            raise ValueError("This file could not be read as text.") from exc
    if not text or not text.strip():
        raise ValueError("No readable content was provided.")
    return IngestionResult(
        document_id=str(uuid.uuid4()),
        input_type=input_type,
        filename=filename,
        language=_language(text),
        text=text,
        pages=[PageText(page=1, text=text)],
        warnings=["Mock ingestion: page mapping and OCR are not implemented."],
    )
