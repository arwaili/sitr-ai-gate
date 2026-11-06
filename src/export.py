"""Safe copies the user can take to an outside AI assistant: redacted text and redacted PDFs.

A redacted PDF is offered only after it is read back and none of the found values remain.
"""

import re
import tempfile
from pathlib import Path

import pymupdf

from src.contracts import RedactionResult

_EXPORT_DIR = Path(tempfile.gettempdir()) / "sitr-exports"
# Numbers inside a value (IDs, salaries, phone groups) are searched and checked on their own,
# because a PDF can store a mixed Arabic line in a different order than it reads.
_NUMBER = re.compile(r"\d[\d,.]*\d")


def _pieces(value: str) -> set[str]:
    return {p.strip() for p in (value, *value.splitlines(), *_NUMBER.findall(value)) if p.strip()}


def _leaks(value: str, text: str) -> bool:
    return value in text or any(number in text for number in _NUMBER.findall(value))


def _target(name: str, suffix: str) -> Path:
    folder = Path(tempfile.mkdtemp(dir=_EXPORT_DIR.mkdir(exist_ok=True) or _EXPORT_DIR))
    return folder / f"{Path(name).stem}-redacted{suffix}"


def redacted_text_file(redaction: RedactionResult, name: str = "message") -> Path:
    path = _target(name, ".txt")
    path.write_text(redaction.safe_text, encoding="utf-8")
    return path


def redacted_pdf(source: str, redaction: RedactionResult) -> Path | None:
    """Black out every replaced value in the PDF; None if any value could not be removed."""
    values = {r.original_value: r.placeholder for r in redaction.replacements}
    path = _target(Path(source).name, ".pdf")
    try:
        with pymupdf.open(source) as doc:
            for page in doc:
                for value, placeholder in values.items():
                    for piece in _pieces(value):
                        for rect in page.search_for(piece):
                            page.add_redact_annot(rect, text=placeholder, fill=(0, 0, 0),
                                                  text_color=(1, 1, 1))
                page.apply_redactions()
            doc.save(path, garbage=4, deflate=True)
        with pymupdf.open(path) as check:
            remaining = "\n".join(page.get_text() for page in check)
    except Exception:
        path.unlink(missing_ok=True)
        return None
    if any(_leaks(value, remaining) for value in values):
        path.unlink(missing_ok=True)
        return None
    return path
