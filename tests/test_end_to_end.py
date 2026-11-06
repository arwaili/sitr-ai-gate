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
        ("Safe public prompt", "allow", "ALLOWED"),
        ("Synthetic CV", "redact", "REDACTED"),
        ("Synthetic Arabic-English contract", "private", "PRIVATE ROUTE"),
        ("Code with a synthetic API key", "block", "BLOCKED"),
    ],
)
def test_each_demo_example_reaches_its_decision(name: str, action: str, label: str) -> None:
    result = inspect_and_process(text=EXAMPLES[name])
    assert result["action_taken"] == action
    badge, why, _, _, response, models = render(result)
    assert label in badge
    assert "**Risk:**" in why
    assert "Detector:" in models
    if action == "block":
        assert response == "No model was called."


def test_error_renders_without_a_risk_claim() -> None:
    badge, why, original, safe_text, response, _ = render(inspect_and_process(text=" "))
    assert "ERROR" in badge
    assert "Not assessed" in why
    assert (original, safe_text) == ([], "")
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
    assert "REDACTED" in outputs[0]
    assert outputs[2].rtl is False  # the CV starts in English
    assert outputs[-1] is None  # the file box is cleared
    assert not upload.exists()
    app.analyze(EXAMPLES["Code with a synthetic API key"], None, "summarize")
    dashboard = app.dashboard()
    assert "Inspected · فُحص<b>2</b>" in dashboard
    assert "Redacted · منقّح<b>1</b>" in dashboard and "Blocked · محظور<b>1</b>" in dashboard
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
    _, why, _, _, _, details = render(result)
    assert "EMAIL × 1" in why and "Sanitized external" in why
    assert "| EMAIL | medium | regex |" in details
    assert "test.applicant@example.com" not in details


def test_blocked_route_says_no_model_was_called() -> None:
    result = inspect_and_process(text=EXAMPLES["Code with a synthetic API key"])
    _, why, _, _, response, _ = render(result)
    assert "no model was called" in why
    assert response == "No model was called."
