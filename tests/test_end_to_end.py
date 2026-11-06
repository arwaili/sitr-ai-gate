import re
import shutil
from pathlib import Path

import pytest

from src.orchestrator import inspect_and_process

gradio = pytest.importorskip("gradio")  # CI installs only the core test dependencies.

import app  # noqa: E402
from app import EXAMPLES  # noqa: E402


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch) -> None:
    # CI has no model libraries, and a detector that cannot run now blocks, so switch models off.
    monkeypatch.setenv("SITR_HF_MODELS", "0")
    monkeypatch.setattr(app, "_stats", app.Counter())
    monkeypatch.setattr(app, "_entity_stats", app.Counter())


def _chat(text: str | None = None, path: str | None = None, task: str = "summarize",
          lang: str = "en") -> list:
    message = {"text": text or "", "files": [path] if path else []}
    return list(app.send(message, task, [], lang))


@pytest.mark.parametrize(
    ("name", "action", "word"),
    [
        ("Safe public prompt", "allow", "Allowed"),
        ("Synthetic CV", "redact", "Redacted"),
        ("Synthetic Arabic-English contract", "private", "Private route"),
        ("Code with a synthetic API key", "block", "Blocked"),
    ],
)
def test_each_example_gets_its_decision_card(name: str, action: str, word: str) -> None:
    result = inspect_and_process(text=EXAMPLES[name])
    assert result["action_taken"] == action
    card = app.reply(result)
    assert f'class="sitr-seal {action}"' in card and word in card
    assert "What Sitr found" in card and f'class="sitr-next {action}"' in card


def test_reply_runs_in_order_decision_findings_sent_answer() -> None:
    card = app.reply(inspect_and_process(text=EXAMPLES["Synthetic CV"]))
    order = [card.index(marker) for marker in
             ("sitr-seal", "sitr-next", "What Sitr found", "Answer", "Technical details")]
    assert order == sorted(order)


def test_redacted_reply_shows_placeholders_as_what_was_sent() -> None:
    card = app.reply(inspect_and_process(text=EXAMPLES["Synthetic CV"]))
    to_send = card.split('class="sitr-next')[1].split("What Sitr found")[0]
    assert "Send this version instead" in to_send
    assert "[EMAIL_1]" in to_send and "test.applicant@example.com" not in to_send
    assert '<mark class="medium">test.applicant@example.com<small>EMAIL</small></mark>' in card


def test_blocked_reply_says_nothing_was_sent_and_has_no_answer() -> None:
    card = app.reply(inspect_and_process(text=EXAMPLES["Code with a synthetic API key"]))
    to_send = card.split('class="sitr-next')[1].split("What Sitr found")[0]
    assert "Don&#x27;t send this" in to_send
    assert "[API_KEY_1]" in to_send and "sk-synthetic" not in to_send
    assert "<h4>Answer</h4>" not in card


def test_error_reply_is_not_assessed() -> None:
    card = app.reply(inspect_and_process(text=" "))
    assert 'class="sitr-seal error"' in card and "Not assessed" in card


def test_user_text_and_model_answer_are_escaped() -> None:
    result = inspect_and_process(text="<script>alert(1)</script> hello")
    item = {"text": result["redaction"]["original_text"], "filename": None, "task": "summarize",
            "result": result}
    rendered = "".join(m["content"] for m in app.messages([item]))
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered


def test_send_shows_the_message_first_then_the_reply(tmp_path) -> None:
    upload = Path(shutil.copy(Path("examples/synthetic_cv.pdf"), tmp_path / "cv.pdf"))
    pending, final = _chat(path=str(upload))
    assert "Checking your message" in pending[0][1]["content"]
    assert "Attached: cv.pdf" in final[0][0]["content"]
    files = [Path(f).name for f in final[2][-1]["files"]]
    assert files == ["cv-redacted.pdf", "cv-redacted.txt"]
    assert {"path": final[2][-1]["files"][0]} in [m["content"] for m in final[0]]
    assert 'class="sitr-seal redact"' in final[0][1]["content"]
    assert final[2][-1]["result"]["action_taken"] == "redact"  # kept for the language switch
    assert not upload.exists()  # the upload is deleted after inspection


def test_allowed_text_is_offered_as_it_is_with_no_files() -> None:
    *_, (chat, _, items, _) = _chat(EXAMPLES["Safe public prompt"], task="answer the request")
    assert "Safe to send" in chat[1]["content"] and items[0]["files"] == []
    assert len(chat) == 2


def test_error_offers_nothing_to_copy() -> None:
    card = app.reply(inspect_and_process(text=" "))
    assert "Nothing to send" in card and "sitr-copy" not in card


def test_empty_message_sends_nothing() -> None:
    [(chat, _, items, _)] = _chat(text="   ")
    assert chat == [] and items == []


def test_dashboard_counts_decisions_and_types_only() -> None:
    _chat(EXAMPLES["Synthetic CV"])
    _chat(EXAMPLES["Code with a synthetic API key"], task="answer the request")
    board = app.dashboard()
    assert "<b>2</b><span>Messages checked</span>" in board
    assert "<b>1</b><span>Redacted</span>" in board and "<b>1</b><span>Blocked</span>" in board
    assert "EMAIL" in board and "sk-synthetic" not in board and "example.com" not in board


def test_empty_dashboard_invites_a_first_message() -> None:
    assert "No inspections yet" in app.dashboard()


def test_task_choices_are_a_fixed_short_list() -> None:
    values = [value for _, value in app.TASKS]
    assert "summarize" in values and len(app.EXAMPLE_TASKS) == len(EXAMPLES)
    assert all(task in values for task in app.EXAMPLE_TASKS)


@pytest.mark.parametrize(
    ("name", "word", "reason"),
    [
        ("Safe public prompt", "مسموح", "لم يُعثر على محتوى حساس."),
        ("Synthetic CV", "منقّح", "وُجدت بيانات شخصية"),
        ("Synthetic Arabic-English contract", "خاص", "المسار الخاص"),
        ("Code with a synthetic API key", "محظور", "مفتاح أو رمز وصول"),
    ],
)
def test_arabic_shows_only_arabic(name: str, word: str, reason: str) -> None:
    card = app.reply(inspect_and_process(text=EXAMPLES[name]), "ar")
    assert word in card and reason in card
    # Leave out the user's own text, the technical panel, and entity codes such as QATAR_ID.
    shown = re.sub(r'<div class="sitr-(?:quote|answer)" dir="auto">.*?</div>|<details>.*?'
                   r"</details>", " ", card, flags=re.S)
    visible = re.sub(r"<[^>]+>|\b[A-Z][A-Z_]+\b", " ", shown)
    leftover = set(re.findall(r"[A-Za-z]{3,}", visible)) - {"Qwen", "Hugging", "Face", "ChatGPT",
                                                           "Claude"}
    assert not leftover, leftover


def test_arabic_error_explains_and_says_nothing_was_sent() -> None:
    result = inspect_and_process(text=" ")
    assert app.reason(result, "ar") == "لا يوجد محتوى قابل للقراءة. لم يُرسل شيء إلى أي نموذج."


def test_language_switch_redraws_the_whole_conversation() -> None:
    *_, (_, _, items, _) = _chat(EXAMPLES["Synthetic CV"])
    outputs = app.switch_language("en", items)
    assert outputs[0] == "ar"
    assert "منقّح" in str(outputs[8].value[1]["content"])  # Gradio stores content as parts
    assert len(outputs) == 17  # one value per component the switch updates
    assert app.switch_language("ar", items)[0] == "en"


def test_both_languages_have_the_same_keys() -> None:
    from ui_text import TEXT

    def shape(value):
        return {k: shape(v) for k, v in value.items()} if isinstance(value, dict) else (
            len(value) if isinstance(value, list) else None)

    assert shape(TEXT["en"]) == shape(TEXT["ar"])


def test_every_example_has_a_label_in_both_languages() -> None:
    for lang in ("en", "ar"):
        labels = [example["display_text"] for example in app.chat_examples(lang)]
        assert len(labels) == len(EXAMPLES) and all(labels)
