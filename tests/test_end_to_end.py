import logging
import re
import shutil
from pathlib import Path

import pytest

from src.orchestrator import inspect_and_process

gradio = pytest.importorskip("gradio")  # CI installs only the core test dependencies.

import app  # noqa: E402


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch) -> None:
    # CI has no model libraries, and a detector that cannot run now blocks, so switch models off.
    monkeypatch.setenv("SITR_HF_MODELS", "0")
    monkeypatch.setattr(app, "_stats", app.Counter())
    monkeypatch.setattr(app, "_entity_stats", app.Counter())


def _ask(text: str = "", path: str | None = None, lang: str = "en") -> list:
    return list(app.send({"text": text, "files": [path] if path else []}, [], lang))


def _visible(html: str) -> str:
    """The answer as the user first sees it, without the collapsed details."""
    shown = re.sub(r"<details.*?</details>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", shown)).strip()


@pytest.mark.parametrize(
    ("index", "action", "headline"),
    [
        (0, "allow", "Yes, you can send it to an AI assistant."),
        (1, "redact", "Not as it is. Send this version to an AI assistant instead."),
        (2, "private", "Better not. Keep this one private."),
        (3, "block", "No, don&#x27;t send this to an AI assistant."),
    ],
)
def test_each_question_gets_a_plain_answer(index: int, action: str, headline: str) -> None:
    example = app.chat_examples()[index]
    *_, (chat, _, items, _) = _ask(example["text"])
    answer = chat[1]["content"]
    assert items[-1]["result"]["action_taken"] == action
    assert f'class="sitr-chip {action}"' in answer and headline in answer


def test_answers_name_what_was_found_in_plain_words() -> None:
    *_, (chat, _, _, _) = _ask(app.chat_examples()[1]["text"])
    assert "It has an email address and a phone number." in _visible(chat[1]["content"])


def test_redacted_answer_offers_only_the_safe_version_without_the_question() -> None:
    *_, (chat, _, items, _) = _ask(app.chat_examples()[1]["text"])
    ready = chat[1]["content"].split('class="sitr-ready"')[1].split("</div></div>")[0]
    assert "[EMAIL_1]" in ready and "test.applicant@example.com" not in ready
    assert "Can I" not in ready
    assert items[-1]["files"] == []  # a typed message gets its safe version as text, no file


def test_blocked_answer_says_no_and_hides_the_secret() -> None:
    *_, (chat, _, _, _) = _ask(app.chat_examples()[3]["text"])
    ready = chat[1]["content"].split('class="sitr-ready"')[1].split("<details")[0]
    assert "[API_KEY_1]" in ready and "sk-synthetic" not in ready


def test_developer_details_are_collapsed() -> None:
    *_, (chat, _, _, _) = _ask(app.chat_examples()[1]["text"])
    shown = _visible(chat[1]["content"])
    for technical in ("Risk", "Reason codes", "Detector", "40 of 100", "regex"):
        assert technical not in shown
    assert "See what I found" in chat[1]["content"]


def test_no_model_is_called_from_the_chat() -> None:
    *_, (_, _, items, _) = _ask(app.chat_examples()[0]["text"])
    assert items[-1]["result"]["model_response"] is None


def test_file_question_checks_the_file_and_offers_redacted_copies(tmp_path) -> None:
    upload = Path(shutil.copy(Path("examples/synthetic_cv.pdf"), tmp_path / "cv.pdf"))
    pending, final = _ask("Can I upload this CV to Claude?", str(upload))
    assert "Checking it" in pending[0][1]["content"]
    assert "Attached: cv.pdf" in final[0][0]["content"]
    assert "Send this version to Claude instead." in final[0][1]["content"]
    names = [Path(f).name for f in final[2][-1]["files"]]
    assert names == ["sitr-redacted.pdf"]  # a PDF comes back as a PDF only
    assert {"path": final[2][-1]["files"][0]} in [m["content"] for m in final[0]]
    assert not upload.exists()  # the upload is deleted after the check


def test_safe_file_can_be_uploaded_as_it_is(tmp_path) -> None:
    upload = Path(shutil.copy(Path("examples/safe_prompt.txt"), tmp_path / "notes.txt"))
    *_, (chat, _, items, _) = _ask("Can I send this to ChatGPT?", str(upload))
    assert "You can upload the original file as it is." in chat[1]["content"]
    assert items[-1]["files"] == []


def test_error_answer_explains_and_offers_nothing_to_copy(tmp_path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"\xff\xfe broken")
    *_, (chat, _, _, _) = _ask("Can I send this?", str(broken))
    assert "I couldn&#x27;t read that." in chat[1]["content"]
    assert "sitr-copy" not in chat[1]["content"]


def test_destination_and_question_detection() -> None:
    assert app.destination("Can I paste this into chatgpt?") == "ChatGPT"
    assert app.destination("هل أرفعه إلى كلود؟", "ar") == "Claude"
    assert app.destination("Is this fine?") == "an AI assistant"
    assert app.split_question("Can I send it?\n\nBody") == ("Can I send it?", "Body")
    assert app.split_question("No question here\n\nBody") == ("", "No question here\n\nBody")


def test_things_joins_findings_naturally() -> None:
    entities = [{"entity_type": k, "start": i} for i, k in enumerate(("PERSON", "EMAIL", "PHONE"))]
    assert app.things(entities) == "a name, an email address and a phone number"
    assert app.things(entities, "ar") == "اسم، بريد إلكتروني ورقم هاتف"
    assert app.things([]) == ""


def test_user_text_is_escaped() -> None:
    *_, (chat, _, _, _) = _ask("<script>alert(1)</script> hello")
    rendered = "".join(m["content"] for m in chat if isinstance(m["content"], str))
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered


def test_empty_message_sends_nothing() -> None:
    [(chat, _, items, _)] = _ask("   ")
    assert chat == [] and items == []


def test_dashboard_counts_decisions_and_types_only() -> None:
    _ask(app.chat_examples()[1]["text"])
    _ask(app.chat_examples()[3]["text"])
    board = app.dashboard()
    assert "<b>2</b><span>Messages checked</span>" in board
    assert "<b>1</b><span>Redacted</span>" in board and "<b>1</b><span>Blocked</span>" in board
    assert "EMAIL" in board and "sk-synthetic" not in board and "example.com" not in board


def test_empty_dashboard_invites_a_first_message() -> None:
    assert "No inspections yet" in app.dashboard()


@pytest.mark.parametrize(
    ("index", "headline"),
    [(0, "نعم، يمكنك إرساله إلى مساعد الذكاء الاصطناعي."), (1, "ليس كما هو."),
     (2, "الأفضل لا. أبقِ هذا خاصًا."), (3, "لا، لا ترسل هذا إلى مساعد الذكاء الاصطناعي.")],
)
def test_arabic_answers_are_in_arabic(index: int, headline: str) -> None:
    *_, (chat, _, _, _) = _ask(app.chat_examples("ar")[index]["text"], lang="ar")
    answer = chat[1]["content"]
    assert headline in answer
    # Leave out the user's own text, entity placeholders and product names; no English remains.
    shown = re.sub(r'<div class="sitr-quote" dir="auto">.*?</div>', " ", _visible(answer),
                   flags=re.S)
    shown = re.sub(r"\[[A-Z_0-9]+\]|\b[A-Z][A-Z_]+\b", " ", shown)
    leftover = set(re.findall(r"[A-Za-z]{3,}", shown)) - {"ChatGPT", "Claude", "IBAN", "API"}
    leftover -= {w for w in re.findall(r"[A-Za-z]{3,}", answer.split("sitr-quote")[-1])}
    assert not leftover, leftover


def test_arabic_error_reason() -> None:
    assert app.reason(inspect_and_process(text=" "), "ar") == (
        "لا يوجد محتوى قابل للقراءة. لم يُرسل شيء إلى أي نموذج.")


def test_language_switch_redraws_the_whole_conversation() -> None:
    *_, (_, _, items, _) = _ask(app.chat_examples()[1]["text"])
    outputs = app.switch_language("en", items)
    assert outputs[0] == "ar"
    assert "ليس كما هو" in str(outputs[8].value[1]["content"])  # Gradio stores content as parts
    assert len(outputs) == 16  # one value per component the switch updates
    assert app.switch_language("ar", items)[0] == "en"


def test_both_languages_have_the_same_keys() -> None:
    from ui_text import TEXT

    def shape(value):
        if isinstance(value, dict):
            return {k: shape(v) for k, v in value.items()}
        return len(value) if isinstance(value, list | tuple) else None

    assert shape(TEXT["en"]) == shape(TEXT["ar"])


def test_every_example_is_a_question_in_both_languages() -> None:
    for lang in ("en", "ar"):
        for example in app.chat_examples(lang):
            question, content = app.split_question(example["text"])
            assert question == example["display_text"] and content


def test_uploads_never_inspected_are_purged() -> None:
    # Regression (R1, Saad): Gradio stores a file on drop, so an abandoned upload stayed on disk.
    assert app.demo.delete_cache is not None


def test_audit_events_are_written_when_enabled(monkeypatch, capfd) -> None:
    # Regression (R1, Saad): nothing enabled INFO, so the app wrote no audit events at all.
    logger = logging.getLogger("sitr")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    app.enable_audit_log()
    app.enable_audit_log()
    assert len(logger.handlers) == 1
    inspect_and_process(text="Curriculum vitae: test.applicant@example.com")
    err = capfd.readouterr().err
    assert '"action": "redact"' in err
    assert "test.applicant" not in err


def test_only_the_content_under_a_question_is_checked(monkeypatch) -> None:
    # Regression (R1): checking the question with the content made the model read "Claude" as
    # a name and miss the real name in the contract, which then leaked into the safe version.
    seen = []
    real = app.inspect_and_process
    monkeypatch.setattr(app, "inspect_and_process",
                        lambda text=None, **kw: seen.append(text) or real(text=text, **kw))
    _ask("Can I upload this to Claude?\n\nEmail: test.applicant@example.com")
    assert seen == ["Email: test.applicant@example.com"]


def test_interface_text_names_no_ai_product() -> None:
    # Product names are trademarks; Sitr names one only when the user's own question does.
    import json

    from ui_text import TEXT
    shown = json.dumps(TEXT, ensure_ascii=False)
    for name in ("ChatGPT", "Claude", "Gemini", "Copilot"):
        assert name not in shown
    assert app.destination("Can I paste this into ChatGPT?") == "ChatGPT"


def test_sidebar_keeps_status_and_toggles_at_the_bottom() -> None:
    assert 'id="sitr-foot"' not in app.brand()  # the footer is its own column, not the brand
    assert "Check before you share" in app.brand() and "افحص قبل أن تشارك" in app.brand("ar")


def test_uploaded_text_file_comes_back_as_redacted_text(tmp_path) -> None:
    upload = tmp_path / "cv.txt"
    upload.write_text("Curriculum vitae: test.applicant@example.com", encoding="utf-8")
    *_, (_, _, items, _) = _ask("Can I send this?", str(upload))
    [safe] = items[-1]["files"]
    assert Path(safe).name == "sitr-redacted.txt"
    assert "test.applicant" not in Path(safe).read_text(encoding="utf-8")


def test_pdf_that_cannot_be_redacted_safely_falls_back_to_text(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app, "redacted_pdf", lambda *_: None)
    upload = Path(shutil.copy(Path("examples/synthetic_cv.pdf"), tmp_path / "cv.pdf"))
    *_, (_, _, items, _) = _ask("Can I send this?", str(upload))
    assert [Path(f).name for f in items[-1]["files"]] == ["sitr-redacted.txt"]
    assert items[-1]["pdf_failed"]
