import logging

import pytest

from src.orchestrator import inspect_and_process

gradio = pytest.importorskip("gradio")  # CI installs only the core test dependencies.

from app import EXAMPLES, analyze, demo, enable_audit_log, highlight, render  # noqa: E402


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


def test_analyze_clears_the_upload_it_deleted(tmp_path) -> None:
    # Regression (R1): the file box kept a deleted path, so a second click failed.
    path = tmp_path / "cv.txt"
    path.write_text("Curriculum vitae: test.applicant@example.com", encoding="utf-8")
    outputs = analyze("", str(path))
    assert not path.exists()
    assert outputs[-1] is None


def test_uploads_never_inspected_are_purged() -> None:
    # Regression (R1): Gradio stores a file on drop, so an abandoned upload stayed on disk.
    assert demo.delete_cache is not None


def test_audit_events_are_written_when_enabled(monkeypatch, capfd) -> None:
    # Regression (R1): nothing enabled INFO, so the app wrote no audit events at all.
    logger = logging.getLogger("sitr")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    enable_audit_log()
    enable_audit_log()
    assert len(logger.handlers) == 1
    inspect_and_process(text="Curriculum vitae: test.applicant@example.com")
    err = capfd.readouterr().err
    assert '"action": "redact"' in err
    assert "test.applicant" not in err
