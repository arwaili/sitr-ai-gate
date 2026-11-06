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
    assert path is not None and path.name == "sitr-redacted.pdf"
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
    path = redacted_text_file(_redaction(("a@example.com", "[EMAIL_1]")))
    assert path.name == "sitr-redacted.txt" and path.read_text(encoding="utf-8") == "safe"


def test_hidden_parts_of_the_pdf_are_scrubbed(tmp_path) -> None:
    # Regression (R1): values were removed from the page text only. Metadata, the outline, links,
    # comments and attachments travel with the file and can hold the same name or email.
    name, email = "Mariam Al-Example", "mariam.al-example@example.com"
    source = tmp_path / "leaky.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"Contact {name} at {email}")
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 60, 300, 80),
                      "uri": f"mailto:{email}"})
    page.add_text_annot((72, 120), f"Ask {name}")
    doc.set_metadata({"author": name, "title": f"CV of {name}", "subject": email})
    doc.set_toc([[1, f"About {name}", 1]])
    doc.embfile_add(f"{name}.txt", email.encode())
    doc.save(source)

    path = redacted_pdf(str(source), _redaction((name, "[PERSON_1]"), (email, "[EMAIL_1]")))
    assert path is not None
    with pymupdf.open(path) as out:
        everything = "\n".join([
            *(page.get_text() for page in out), *map(str, out.metadata.values()),
            out.get_xml_metadata() or "", *(str(e[1]) for e in out.get_toc()),
            *(link.get("uri") or "" for page in out for link in page.get_links()),
            *(a.info.get("content", "") for page in out for a in page.annots() or []),
            *out.embfile_names(),
        ])
    assert name not in everything and email not in everything
    assert "Mariam" not in everything


def test_exported_files_do_not_carry_the_uploaded_name() -> None:
    # Regression (R1): "Mariam_CV.pdf" became "Mariam_CV-redacted.pdf", leaking the name.
    path = redacted_pdf(str(EXAMPLES / "synthetic_cv.pdf"), _redaction(("+974 0000 0100", "[P]")))
    assert path is not None and path.name == "sitr-redacted.pdf"
