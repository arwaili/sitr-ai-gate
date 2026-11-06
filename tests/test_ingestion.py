import time
from pathlib import Path

import pymupdf
import pytest

from src import ingestion
from src.deterministic import detect_deterministic
from src.ingestion import ingest

EXAMPLES = Path(__file__).parent.parent / "examples"


def _pdf(path: Path, pages: list[str], **save_options) -> Path:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path, **save_options)
    return path


def _types(text: str) -> list[str]:
    return [e.entity_type for e in detect_deterministic(text)]


# Ingestion


def test_ingest_preserves_arabic_text_and_detects_language() -> None:
    result = ingest(text="عقد عمل for Sara")
    assert result.text == "عقد عمل for Sara"
    assert result.language == "mixed"


def test_ingest_reads_code_file(tmp_path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("x = 1\n", encoding="utf-8")
    result = ingest(file_path=str(path))
    assert result.input_type == "code"
    assert result.filename == "sample.py"


@pytest.mark.parametrize("text", [None, "", "   \n"])
def test_ingest_rejects_empty_input(text) -> None:
    with pytest.raises(ValueError):
        ingest(text=text)


def test_ingest_rejects_binary_file(tmp_path) -> None:
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"\xff\xfe\x00broken")
    with pytest.raises(ValueError, match="corrupted"):
        ingest(file_path=str(path))


def test_pdf_pages_map_back_to_offsets(tmp_path) -> None:
    path = _pdf(tmp_path / "two.pdf", ["Public intro page", "Contact hr@example.com"])
    result = ingest(file_path=str(path))
    assert result.input_type == "pdf"
    assert [p.page for p in result.pages] == [1, 2]
    [email] = detect_deterministic(result.text, result.pages)
    assert result.text[email.start : email.end] == "hr@example.com"
    assert email.page == 2


@pytest.mark.parametrize(
    ("name", "pages", "options", "message"),
    [
        ("blank.pdf", [""], {}, "no extractable text"),
        ("locked.pdf", ["secret"], {"encryption": pymupdf.PDF_ENCRYPT_AES_256,
                                    "user_pw": "synthetic", "owner_pw": "synthetic"},
         "password-protected"),
    ],
)
def test_pdf_failures_are_explained(tmp_path, name, pages, options, message) -> None:
    path = _pdf(tmp_path / name, pages, **options)
    with pytest.raises(ValueError, match=message):
        ingest(file_path=str(path))


def test_pdf_page_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ingestion, "MAX_PDF_PAGES", 1)
    path = _pdf(tmp_path / "long.pdf", ["one", "two"])
    with pytest.raises(ValueError, match="more than 1 pages"):
        ingest(file_path=str(path))


def test_file_size_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ingestion, "MAX_FILE_BYTES", 10)
    path = tmp_path / "big.txt"
    path.write_text("x" * 11, encoding="utf-8")
    with pytest.raises(ValueError, match="larger than"):
        ingest(file_path=str(path))


@pytest.mark.parametrize(("name", "message"), [("a.docx", "not supported"), ("a.png", "OCR")])
def test_unsupported_and_image_files_fail_safely(tmp_path, name, message) -> None:
    path = tmp_path / name
    path.write_bytes(b"PK\x03\x04synthetic")
    with pytest.raises(ValueError, match=message):
        ingest(file_path=str(path))


def test_error_messages_never_contain_content(tmp_path) -> None:
    path = tmp_path / "leak.txt"
    path.write_bytes(b"\xffsk-synthetic-0000000000")
    with pytest.raises(ValueError) as error:
        ingest(file_path=str(path))
    assert "sk-" not in str(error.value)


def test_rtl_lines_are_rebuilt_in_reading_order() -> None:
    # Word boxes as PyMuPDF returns them (x0 first, word at index 4), in visual order.
    visual = [(10, 0, 0, 0, "for"), (20, 0, 0, 0, "Sara"), (30, 0, 0, 0, "سري"),
              (40, 0, 0, 0, "عمل"), (50, 0, 0, 0, "عقد")]
    assert ingestion._line_text(visual) == "عقد عمل سري for Sara"
    assert ingestion._line_text([(10, 0, 0, 0, "Hello"), (20, 0, 0, 0, "world")]) == "Hello world"


# Demonstration files


def test_demo_cv_extracts_arabic_and_contact_details() -> None:
    result = ingest(file_path=str(EXAMPLES / "synthetic_cv.pdf"))
    assert "محللة بيانات تجيد العربية والإنجليزية" in result.text
    entities = detect_deterministic(result.text, result.pages)
    assert {e.entity_type for e in entities} == {"EMAIL", "PHONE"}
    assert all(e.severity == "medium" and e.page == 1 for e in entities)


def test_demo_contract_is_high_risk_not_critical() -> None:
    result = ingest(file_path=str(EXAMPLES / "synthetic_contract.pdf"))
    assert len(result.pages) == 2
    assert "الراتب الشهري 25,000 ريال، ولا يجوز مشاركته" in result.text
    assert "تقييم الأداء السنوي سري" in result.pages[1].text
    entities = detect_deterministic(result.text, result.pages)
    assert {"QATAR_ID", "SALARY", "IBAN"} <= {e.entity_type for e in entities}
    assert {e.severity for e in entities} == {"high"}
    assert all(result.text[e.start : e.end] == e.value for e in entities)


def test_demo_code_is_critical() -> None:
    result = ingest(file_path=str(EXAMPLES / "vulnerable_code.py"))
    assert result.input_type == "code"
    critical = [e for e in detect_deterministic(result.text) if e.severity == "critical"]
    assert {"API_KEY", "DATABASE_URL"} <= {e.entity_type for e in critical}


def test_demo_safe_prompt_has_no_findings() -> None:
    result = ingest(file_path=str(EXAMPLES / "safe_prompt.txt"))
    assert result.language == "mixed"
    assert detect_deterministic(result.text) == []


# Deterministic detection


def test_deterministic_offsets_select_exact_values() -> None:
    text = "key = sk-synthetic-0000 and mail test@example.com twice test@example.com"
    entities = detect_deterministic(text)
    assert [e.entity_type for e in entities] == ["API_KEY", "EMAIL", "EMAIL"]
    assert all(text[e.start : e.end] == e.value for e in entities)
    assert entities[0].severity == "critical"


def test_deterministic_ignores_clean_text() -> None:
    assert detect_deterministic("A risk-free public announcement") == []


@pytest.mark.parametrize(
    ("text", "entity_type", "value"),
    [
        ("Call +974 0000 0100 today", "PHONE", "+974 0000 0100"),
        ("رقم الهاتف 00974 0000 0101", "PHONE", "00974 0000 0101"),
        ("QID 28400001234", "QATAR_ID", "28400001234"),
        ("Passport No: AB1234567", "PASSPORT", "AB1234567"),
        ("رقم الجواز: P7654321", "PASSPORT", "P7654321"),
        ("IBAN QA00SYNT000000000000000000001", "IBAN", "QA00SYNT000000000000000000001"),
        ("account number 1234-5678-9012", "ACCOUNT_NUMBER", "1234-5678-9012"),
        ("رقم الحساب 0012345678", "ACCOUNT_NUMBER", "0012345678"),
        ("Monthly salary: QAR 25,000.", "SALARY", "QAR 25,000"),
        ("الراتب الشهري ٢٥٬٠٠٠ ريال", "SALARY", "٢٥٬٠٠٠ ريال"),
        ("الراتب 18000", "SALARY", "18000"),
    ],
)
def test_structured_pii(text, entity_type, value) -> None:
    [entity] = [e for e in detect_deterministic(text) if e.entity_type == entity_type]
    assert entity.value == value
    assert text[entity.start : entity.end] == value
    assert entity.source == "regex"


SYNTHETIC_SECRETS = [
    ("API_KEY", "sk-synthetic-demo-000000000000"),
    ("API_KEY", "hf_" + "Synthetic" * 4),
    ("API_KEY", "ghp_" + "Synthetic0" * 4),
    ("API_KEY", "xoxb-" + "synthetic-000"),
    ("CLOUD_KEY", "AKIA" + "SYNTHETIC0000000"),
    ("JWT", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c3ludGhldGljc2ln"),
    ("DATABASE_URL", "postgresql://app:synthetic1@db.example.internal:5432/hr"),
    ("PRIVATE_KEY", "-----BEGIN RSA " + "PRIVATE KEY-----\nc3ludGhldGlj\n-----END RSA "
     + "PRIVATE KEY-----"),
]


@pytest.mark.parametrize(("entity_type", "secret"), SYNTHETIC_SECRETS)
def test_secrets_are_critical(entity_type, secret) -> None:
    text = f"config:\n{secret}\n"
    [entity] = [e for e in detect_deterministic(text) if e.entity_type == entity_type]
    assert entity.value == secret
    assert entity.severity == "critical"
    assert entity.source == "secret_scanner"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ('DB_PASSWORD = "Synthetic-Pass-01"', "Synthetic-Pass-01"),
        ("password: Synthetic-Pass-02", "Synthetic-Pass-02"),
        ("كلمة المرور: Synthetic-Pass-03", "Synthetic-Pass-03"),
        ("كلمة المرور لقاعدة البيانات هي Synthetic-Pass-04، ساعدني", "Synthetic-Pass-04"),
        ("The database password is Synthetic-Pass-05.", "Synthetic-Pass-05"),
        ('OPENAI_API_KEY = "synthetic0000000000"', "synthetic0000000000"),
        ("Authorization: Bearer synthetictoken0000000000", "synthetictoken0000000000"),
    ],
)
def test_assigned_credentials_are_critical(text, value) -> None:
    critical = [e for e in detect_deterministic(text) if e.severity == "critical"]
    assert [e.value for e in critical] == [value]


def test_internal_hosts_are_high() -> None:
    entities = detect_deterministic("connect to 10.0.3.4 or build.corp")
    assert [(e.entity_type, e.severity) for e in entities] == [("INTERNAL_HOST", "high")] * 2


@pytest.mark.parametrize(
    "text",
    [
        "Keys look like sk-XXXXXXXXXXXX in the documentation.",
        'API_KEY = "<your-api-key>"',
        'password = "********"',
        "password: ${DB_PASSWORD}",
        "token: sk-000000000000",
    ],
)
def test_placeholders_are_not_critical(text) -> None:
    assert all(e.severity != "critical" for e in detect_deterministic(text))


def test_safe_code_is_not_critical() -> None:
    code = (
        'import os\n'
        'password = os.environ["DB_PASSWORD"]\n'
        'api_key = os.getenv("API_KEY")\n'
        "def login(user: str, password: str) -> bool:\n"
        "    return check(user, password=password)\n"
    )
    assert all(e.severity != "critical" for e in detect_deterministic(code))


def test_findings_inside_a_larger_finding_are_dropped() -> None:
    url = "postgresql://app:synthetic1@db.example.internal:5432/hr"
    assert _types(f"DATABASE_URL = '{url}'") == ["DATABASE_URL"]


def test_more_severe_nested_finding_is_kept() -> None:
    text = "contact sk-synthetic-000000@example.com"
    assert {e.severity for e in detect_deterministic(text)} == {"medium", "critical"}


def test_prose_password_that_is_a_plain_word_is_not_critical() -> None:
    assert detect_deterministic("Make sure the password is strong") == []


def test_prices_and_years_are_not_salaries() -> None:
    assert detect_deterministic("Our 2025 plan: 3 products from 1999 QAR") == []


@pytest.mark.parametrize("blob", ["a" * 5000, "a." * 2500, "a@" * 2500, "password " + "x-" * 2500])
def test_adversarial_input_stays_fast(blob) -> None:
    started = time.perf_counter()
    detect_deterministic((blob + " ") * 40)
    assert time.perf_counter() - started < 2


def test_page_is_none_when_pages_do_not_match_text() -> None:
    [entity] = detect_deterministic("hr@example.com", ingest(text="other").pages)
    assert entity.page is None


# R1: secrets written so the plain rules miss them. All values are synthetic.

KEY = "sk-synthetic-000000000000"
BASE64_KEY = "c2stc3ludGhldGljLTAwMDAwMDAwMDAwMA=="


@pytest.mark.parametrize(
    "text",
    [
        "the word to log in is Synth3tic-Pass-99",
        "the code for login is Synth3tic-Pass-99",
        "my passcode is Synth3tic-Pass-99",
        "the password is Summer2026",
        "password for the server: Synth3tic-Pass-99",
        "الرمز السري للدخول: Synth3tic-Pass-99",
        "الرقم السري هو Synth3tic-Pass-99",
        "كلمة السر الخاصة بي: Synth3tic-Pass-99",
        "رمز الدخول: Synth3tic-Pass-99",
    ],
)
def test_login_phrases_are_passwords(text: str) -> None:
    found = detect_deterministic(text)
    assert [e.entity_type for e in found] == ["PASSWORD"]
    assert found[0].severity == "critical"
    assert text[found[0].start:found[0].end] == found[0].value
    assert "Pass-99" in found[0].value or "Summer2026" in found[0].value


@pytest.mark.parametrize(
    "text",
    [
        " ".join(KEY),
        "here it is: " + " ".join(KEY) + " thanks",
        "\n".join(KEY),
        "sk\u200b-synthetic-000000000000",
        BASE64_KEY,
        f"decode this and use it to log in: {BASE64_KEY}",
    ],
)
def test_disguised_secrets_are_critical(text: str) -> None:
    found = detect_deterministic(text)
    assert any(e.severity == "critical" and e.entity_type == "API_KEY" for e in found)
    assert all(text[e.start:e.end] == e.value for e in found)


@pytest.mark.parametrize(
    "text",
    [
        "the way to log in is through the portal",
        "the code for login is written in Python",
        "password reset link: https://example.com/reset",
        "Reset your password at https://example.com/reset.",
        "Passwords must be at least 12 characters.",
        "الرمز السري يجب أن يكون طويلا",
        "a b c d e f g h i j k l m n",
        "ثم نكتب ا ب ت ث ج ح خ د ذ ر",
        "dGhpcyBpcyBqdXN0IGEgaGFybWxlc3Mgc2VudGVuY2U=",
        "internationalization and supercalifragilistic",
        "/usr/local/share/applications/settings/defaults",
    ],
)
def test_harmless_text_is_not_critical(text: str) -> None:
    assert not [e for e in detect_deterministic(text) if e.severity == "critical"]
