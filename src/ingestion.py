"""Lane 1 ingestion: pasted text, text and code files, and digital PDFs through PyMuPDF."""

import re
import unicodedata
import uuid
from pathlib import Path

import pymupdf

from src.contracts import IngestionResult, PageText

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 50
# Pages are joined with this separator, so offsets into the full text map back to pages.
PAGE_SEPARATOR = "\n\n"

_TEXT_SUFFIXES = {"", ".txt", ".md", ".csv", ".log"}
_CODE_SUFFIXES = {
    ".py", ".js", ".ts", ".java", ".go", ".sh", ".env", ".yml", ".yaml", ".json",
    ".sql", ".toml", ".ini", ".cfg", ".tf", ".rb", ".php", ".cs", ".c", ".cpp",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_ARABIC = re.compile(r"[؀-ۿﭐ-﷿ﹰ-﻿]")


def _language(text: str) -> str:
    has_arabic = bool(_ARABIC.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    return "en" if has_latin else "unknown"


def _is_arabic(word: str) -> bool:
    return bool(_ARABIC.search(word))


def _line_text(words: list[tuple]) -> str:
    """Rebuild one line in reading order from word boxes. PDFs store Arabic in visual order."""
    rtl = sum(_is_arabic(w[4]) for w in words) * 2 > len(words)
    ordered = sorted(words, key=lambda w: -w[0] if rtl else w[0])
    # Runs in the other direction (English inside Arabic, or the reverse) read the other way.
    runs: list[list[str]] = []
    for w in ordered:
        if runs and _is_arabic(w[4]) != rtl and _is_arabic(runs[-1][-1]) != rtl:
            runs[-1].append(w[4])
        else:
            runs.append([w[4]])
    return " ".join(" ".join(run[::-1] if _is_arabic(run[0]) != rtl else run) for run in runs)


def _page_text(page) -> str:
    lines: dict[tuple[int, int], list[tuple]] = {}
    for word in page.get_text("words"):
        lines.setdefault((word[5], word[6]), []).append(word)
    return "\n".join(_line_text(words) for words in lines.values())


def _read_pdf(path: Path) -> list[PageText]:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as exc:
        raise ValueError("This PDF could not be read. It may be corrupted.") from exc
    with doc:
        if doc.needs_pass:
            raise ValueError("This PDF is password-protected.")
        if doc.page_count > MAX_PDF_PAGES:
            raise ValueError(f"This PDF has more than {MAX_PDF_PAGES} pages.")
        try:
            raw_pages = [_page_text(page) for page in doc]
        except Exception as exc:
            raise ValueError("This PDF could not be read. It may be corrupted.") from exc
    # NFKC folds Arabic presentation forms, which many PDF writers emit, back to normal letters.
    return [
        PageText(page=number, text=unicodedata.normalize("NFKC", raw).strip())
        for number, raw in enumerate(raw_pages, start=1)
    ]


def _read_file(path: Path) -> tuple[str, list[PageText]]:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        # shortcut: OCR is optional in the plan and not built, add it behind a flag if time allows
        raise ValueError("Images need OCR, which is not enabled in this demo.")
    if suffix != ".pdf" and suffix not in _TEXT_SUFFIXES | _CODE_SUFFIXES:
        raise ValueError("This file type is not supported.")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("This file could not be read.") from exc
    if size > MAX_FILE_BYTES:
        raise ValueError(f"This file is larger than the {MAX_FILE_BYTES >> 20} MB limit.")
    if suffix == ".pdf":
        pages = _read_pdf(path)
        if not any(page.text for page in pages):
            raise ValueError("This PDF has no extractable text. Scanned PDFs need OCR.")
        return "pdf", pages
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("This file could not be read as text.") from exc
    return ("code" if suffix in _CODE_SUFFIXES else "text"), [PageText(page=1, text=text)]


def ingest(text: str | None = None, file_path: str | None = None) -> IngestionResult:
    """Normalize pasted text or one file. Raises ValueError with a content-free message."""
    filename = None
    input_type = "text"
    if file_path:
        path = Path(file_path)
        filename = path.name
        input_type, pages = _read_file(path)
        text = PAGE_SEPARATOR.join(page.text for page in pages)
    else:
        pages = [PageText(page=1, text=text or "")]
    if not text or not text.strip():
        raise ValueError("No readable content was provided.")
    return IngestionResult(
        document_id=str(uuid.uuid4()),
        input_type=input_type,
        filename=filename,
        language=_language(text),
        text=text,
        pages=pages,
    )
