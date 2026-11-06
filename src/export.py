"""Safe copies the user can take to an outside AI assistant: redacted text and redacted PDFs.

A redacted PDF is offered only after it is read back and none of the found values remain, in
the page text or anywhere else the file can carry text (metadata, outline, links, attachments).
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


def _target(suffix: str) -> Path:
    # A fixed name: the uploaded file's name can itself hold a person's name.
    folder = Path(tempfile.mkdtemp(dir=_EXPORT_DIR.mkdir(exist_ok=True) or _EXPORT_DIR))
    return folder / f"sitr-redacted{suffix}"


def _all_text(doc) -> str:
    """Everything in the PDF a reader or an AI assistant could see as text."""
    parts = [page.get_text() for page in doc]
    parts += [str(v) for v in doc.metadata.values() if v]
    parts.append(doc.get_xml_metadata() or "")
    parts += [str(entry[1]) for entry in doc.get_toc()]
    for page in doc:
        parts += [link.get("uri") or "" for link in page.get_links()]
        parts += [annot.info.get("content", "") for annot in page.annots() or []]
    parts += list(doc.embfile_names())
    return "\n".join(parts)


def redacted_text_file(redaction: RedactionResult) -> Path:
    path = _target(".txt")
    path.write_text(redaction.safe_text, encoding="utf-8")
    return path


def redacted_pdf(source: str, redaction: RedactionResult) -> Path | None:
    """Black out every replaced value in the PDF; None if any value could not be removed."""
    values = {r.original_value: r.placeholder for r in redaction.replacements}
    path = _target(".pdf")
    try:
        with pymupdf.open(source) as doc:
            for page in doc:
                # Links and comments can hold values too (mailto: addresses), so they go.
                for link in page.get_links():
                    page.delete_link(link)
                for annot in list(page.annots() or []):
                    page.delete_annot(annot)
                for value, placeholder in values.items():
                    for piece in _pieces(value):
                        for rect in page.search_for(piece):
                            page.add_redact_annot(rect, text=placeholder, fill=(0, 0, 0),
                                                  text_color=(1, 1, 1))
                page.apply_redactions()
            # Author, title, outline and attachments are not page text but travel with the file.
            doc.set_metadata({})
            doc.del_xml_metadata()
            doc.set_toc([])
            for name in doc.embfile_names():
                doc.embfile_del(name)
            doc.save(path, garbage=4, deflate=True, clean=True)
        with pymupdf.open(path) as check:
            remaining = _all_text(check)
    except Exception:
        path.unlink(missing_ok=True)
        return None
    if any(_leaks(value, remaining) for value in values):
        path.unlink(missing_ok=True)
        return None
    return path
