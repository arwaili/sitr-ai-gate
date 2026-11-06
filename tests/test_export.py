from pathlib import Path

import pymupdf

from src.contracts import RedactionResult, Replacement
from src.export import _leaks, redacted_pdf, redacted_text_file

EXAMPLES = Path(__file__).parent.parent / "examples"


def _redaction(*pairs: tuple[str, str]) -> RedactionResult:
    return RedactionResult(
        original_text="", safe_text="safe",
        replacements=[Replacement(placeholder=p, entity_type="X", original_value=v)
                      for v, p in pairs],
    )


def test_redacted_pdf_removes_every_value_including_arabic_line_numbers() -> None:
    redaction = _redaction(("28400001234", "[QATAR_ID_1]"), ("QAR 25,000", "[SALARY_1]"),
                           ("25,000 ريال", "[SALARY_2]"),
                           ("QA00SYNT000000000000000000001", "[IBAN_1]"))
    path = redacted_pdf(str(EXAMPLES / "synthetic_contract.pdf"), redaction)
    assert path is not None and path.name == "synthetic_contract-redacted.pdf"
    text = "\n".join(page.get_text() for page in pymupdf.open(path))
    for value in ("28400001234", "25,000", "QA00SYNT000000000000000000001"):
        assert value not in text
    assert "[QATAR_ID_1]" in text


def test_redacted_pdf_is_refused_when_a_value_cannot_be_removed(monkeypatch) -> None:
    monkeypatch.setattr("src.export.pymupdf.Page.search_for", lambda self, text: [])
    path = redacted_pdf(str(EXAMPLES / "synthetic_cv.pdf"), _redaction(("+974 0000 0100", "[P]")))
    assert path is None


def test_broken_pdf_gives_no_redacted_copy(tmp_path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 broken")
    assert redacted_pdf(str(broken), _redaction(("x@example.com", "[EMAIL_1]"))) is None


def test_leak_check_catches_numbers_on_their_own() -> None:
    assert _leaks("25,000 ريال", "ريال، ولا 25,000 الراتب")
    assert not _leaks("25,000 ريال", "[SALARY_1] ريال")


def test_redacted_text_file_holds_only_the_safe_text() -> None:
    path = redacted_text_file(_redaction(("a@example.com", "[EMAIL_1]")), "notes.txt")
    assert path.name == "notes-redacted.txt" and path.read_text(encoding="utf-8") == "safe"
