import pytest

from src.orchestrator import inspect_and_process

gradio = pytest.importorskip("gradio")  # CI installs only the core test dependencies.

from app import EXAMPLES, highlight, render  # noqa: E402


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
