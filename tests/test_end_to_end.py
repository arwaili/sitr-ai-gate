import pytest

from src.orchestrator import inspect_and_process

gradio = pytest.importorskip("gradio")  # CI installs only the core test dependencies.

from app import EXAMPLES, highlight, render  # noqa: E402


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch) -> None:
    # CI has no model libraries, and a detector that cannot run now blocks, so switch models off.
    monkeypatch.setenv("SITR_HF_MODELS", "0")


@pytest.mark.parametrize(
    ("name", "action", "label"),
    [
        ("Safe public prompt", "allow", "Allowed"),
        ("Synthetic CV", "redact", "Redacted"),
        ("Synthetic Arabic-English contract", "private", "Private route"),
        ("Code with a synthetic API key", "block", "Blocked"),
    ],
)
def test_each_demo_example_reaches_its_decision(name: str, action: str, label: str) -> None:
    result = inspect_and_process(text=EXAMPLES[name])
    assert result["action_taken"] == action
    seal, facts, _, _, response, details = render(result)
    assert f'class="sitr-seal {action}"' in seal and label in seal
    assert "<dt>Risk</dt>" in facts
    assert "Detector:" in details
    if action == "block":
        assert response == "No model was called."


def test_error_renders_without_a_risk_claim() -> None:
    seal, facts, original, safe_text, response, _ = render(inspect_and_process(text=" "))
    assert 'class="sitr-seal error"' in seal and "Not inspected" in seal
    assert "Not assessed" in facts
    assert original == [] and safe_text.startswith("Nothing")
    assert response == "No model was called."


def test_highlight_rebuilds_text_and_skips_overlaps() -> None:
    entities = [
        {"start": 0, "end": 4, "entity_type": "A"},
        {"start": 2, "end": 6, "entity_type": "B"},
        {"start": 7, "end": 8, "entity_type": "C"},
    ]
    segments = highlight("abcdefgh", entities)
    assert "".join(part for part, _ in segments) == "abcdefgh"
    assert [label for _, label in segments if label] == ["A", "C"]


def test_analyze_counts_decisions_clears_the_upload_and_deletes_it(tmp_path, monkeypatch) -> None:
    import shutil
    from pathlib import Path

    import app

    monkeypatch.setattr(app, "_stats", app.Counter())
    monkeypatch.setattr(app, "_entity_stats", app.Counter())
    upload = Path(shutil.copy(Path("examples/synthetic_cv.pdf"), tmp_path / "cv.pdf"))
    outputs = app.analyze("", str(upload), "summarize")
    assert 'class="sitr-seal redact"' in outputs[0]
    assert outputs[2].rtl is False  # the CV starts in English
    assert outputs[-2] is None  # the file box is cleared
    assert outputs[-1]["action_taken"] == "redact"  # kept for the language switch
    assert not upload.exists()
    app.analyze(EXAMPLES["Code with a synthetic API key"], None, "summarize")
    dashboard = app.dashboard()
    assert "<b>2</b> inspected" in dashboard
    assert "Redacted<b>1</b>" in dashboard and "Blocked<b>1</b>" in dashboard
    assert "EMAIL" in dashboard and "API_KEY" in dashboard
    assert "sk-synthetic" not in dashboard and "example.com" not in dashboard


def test_text_direction_follows_the_first_letter() -> None:
    import app

    assert app.starts_rtl("  عقد عمل / Employment contract")
    assert not app.starts_rtl("Employment contract / عقد عمل")
    assert not app.starts_rtl("12345")


def test_task_choices_are_a_fixed_short_list() -> None:
    import app

    values = [value for _, value in app.TASKS]
    assert "summarize" in values
    assert all(len(value) <= 40 for value in values)


def test_details_list_findings_without_their_values() -> None:
    result = inspect_and_process(text=EXAMPLES["Synthetic CV"])
    _, facts, _, _, _, details = render(result)
    assert "EMAIL × 1" in facts and "placeholders only" in facts
    assert "| EMAIL | medium | regex |" in details
    assert "test.applicant@example.com" not in details


def test_blocked_route_says_no_model_was_called() -> None:
    result = inspect_and_process(text=EXAMPLES["Code with a synthetic API key"])
    _, facts, _, _, response, _ = render(result)
    assert "<dd>No model</dd>" in facts
    assert response == "No model was called."


def test_empty_dashboard_invites_a_first_inspection(monkeypatch) -> None:
    import app

    monkeypatch.setattr(app, "_stats", app.Counter())
    assert "No inspections yet" in app.dashboard()


def test_every_entity_type_the_detectors_emit_has_a_color() -> None:
    import app
    from src.hf_detection import LABEL_MAP

    assert {kind for kind, _ in LABEL_MAP.values()} <= set(app.COLOR_MAP)


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
    import re

    seal, facts, _, _, _, details = render(inspect_and_process(text=EXAMPLES[name]), "ar")
    assert word in seal and reason in seal
    # Entity codes such as QATAR_ID and the model names stay as they are; no other English.
    visible = re.sub(r"<[^>]+>|\b[A-Z][A-Z_]+\b", " ", seal + facts)
    leftover = set(re.findall(r"[A-Za-z]{3,}", visible)) - {"Qwen", "Hugging", "Face"}
    assert not leftover, leftover
    assert "الكاشف" in details


def test_arabic_error_explains_and_says_nothing_was_sent() -> None:
    import app

    result = inspect_and_process(text=" ")
    assert app.reason(result, "ar") == "لا يوجد محتوى قابل للقراءة. لم يُرسل شيء إلى أي نموذج."


def test_language_switch_relabels_everything_and_keeps_the_last_result() -> None:
    import app

    result = inspect_and_process(text=EXAMPLES["Synthetic CV"])
    outputs = app.switch_language("en", result)
    assert outputs[0] == "ar"
    assert "منقّح" in outputs[15]  # the seal is redrawn in Arabic
    back = app.switch_language("ar", result)
    assert back[0] == "en" and "Redacted" in back[15]
    assert len(outputs) == 26  # one value per component the switch updates


def test_both_languages_have_the_same_keys() -> None:
    from ui_text import TEXT

    def shape(value):
        return {k: shape(v) for k, v in value.items()} if isinstance(value, dict) else (
            len(value) if isinstance(value, list) else None)

    assert shape(TEXT["en"]) == shape(TEXT["ar"])
