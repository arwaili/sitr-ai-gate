import json
import logging

import pytest

from src import router
from src.contracts import FinalResponse, SensitiveEntity
from src.orchestrator import inspect_and_process
from src.redactor import redact

CV = "Curriculum vitae: Mariam, test.applicant@example.com, +974 5555 0100"
CONTRACT = "عقد عمل: الراتب 15000 ريال، الرقم الشخصي 28400000000"
LEAKY_CODE = 'API_KEY = "sk-synthetic-000000000000"\nprint(API_KEY)'


@pytest.mark.parametrize(
    ("scenario", "text", "risk", "action"),
    [
        ("T1", "Write a public marketing slogan for a Doha cafe.", "low", "allow"),
        ("T2", CV, "medium", "redact"),
        ("T3", CONTRACT, "high", "private"),
        ("T4", LEAKY_CODE, "critical", "block"),
        ("T5", "def add(a, b):\n    return a + b\n", "low", "allow"),
        ("T6", "Employee evaluation تقييم الموظف: needs coaching", "high", "private"),
    ],
)
def test_shared_matrix(scenario: str, text: str, risk: str, action: str) -> None:
    result = inspect_and_process(text=text)
    FinalResponse.model_validate(result)
    assert result["analysis"]["risk_level"] == risk, scenario
    assert result["action_taken"] == action, scenario


@pytest.mark.xfail(reason="T7 needs the real secret scanner, the mock flags any key-shaped text")
def test_t7_documentation_key_is_not_critical() -> None:
    result = inspect_and_process(text="Keys look like sk-XXXXXXXXXXXX in the documentation.")
    assert result["analysis"]["risk_level"] != "critical"


@pytest.mark.parametrize("text", [None, "", "  \n"])
def test_t8_empty_input_is_an_explained_error(text) -> None:
    result = inspect_and_process(text=text)
    FinalResponse.model_validate(result)
    assert result["status"] == "error"
    assert result["model_response"] is None
    assert result["user_message"]


def test_t8_corrupted_file_is_an_explained_error(tmp_path) -> None:
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"\xff\xfe\x00broken")
    result = inspect_and_process(file_path=str(path))
    assert result["status"] == "error"
    assert "\xff" not in result["user_message"]


def test_blocked_secret_never_reaches_a_model() -> None:
    result = inspect_and_process(text=LEAKY_CODE)
    assert result["status"] == "blocked"
    assert result["model_response"] is None
    assert "sk-synthetic" not in result["user_message"]
    assert "sk-synthetic" not in result["redaction"]["safe_text"]


def test_redaction_is_stable_for_repeated_values() -> None:
    text = "a@example.com, b@example.com, a@example.com"
    redaction = inspect_and_process(text=text)["redaction"]
    assert redaction["safe_text"] == "[EMAIL_1], [EMAIL_2], [EMAIL_1]"
    assert [item["original_value"] for item in redaction["replacements"]] == [
        "a@example.com",
        "b@example.com",
    ]


@pytest.fixture
def model_calls(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        router, "call_model", lambda route, prompt, intent: calls.append((route, prompt)) or "ok"
    )
    return calls


def test_critical_input_never_reaches_any_model(model_calls) -> None:
    inspect_and_process(text=LEAKY_CODE)
    inspect_and_process(text=f"{CONTRACT}\n{LEAKY_CODE}")
    assert model_calls == []


def test_high_risk_original_goes_only_to_the_private_route(model_calls) -> None:
    inspect_and_process(text=CONTRACT)
    assert model_calls == [("private_simulation", CONTRACT)]


def test_redact_route_receives_no_detected_value(model_calls) -> None:
    result = inspect_and_process(text=CV)
    [(route, prompt)] = model_calls
    assert route == "sanitized_external"
    for entity in result["analysis"]["entities"]:
        assert entity["value"] not in prompt


def test_unexpected_failure_fails_closed(monkeypatch, model_calls) -> None:
    def explode(*_):
        raise RuntimeError(LEAKY_CODE)

    monkeypatch.setattr("src.orchestrator.decide", explode)
    result = inspect_and_process(text=CV)
    assert (result["status"], result["action_taken"]) == ("error", "block")
    assert "sk-synthetic" not in result["user_message"]
    assert model_calls == []


def test_audit_log_contains_metadata_only(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="sitr.audit"):
        inspect_and_process(text=CV)
        inspect_and_process(text=LEAKY_CODE)
    events = [json.loads(record.message) for record in caplog.records]
    assert [event["action"] for event in events] == ["redact", "block"]
    assert events[0]["entity_counts"] == {"EMAIL": 1, "PHONE": 1}
    logged = caplog.text
    for secret in ("test.applicant@example.com", "5555 0100", "sk-synthetic", "Mariam"):
        assert secret not in logged


def _entity(entity_type: str, text: str, value: str) -> SensitiveEntity:
    start = text.index(value)
    return SensitiveEntity(
        entity_type=entity_type,
        value=value,
        start=start,
        end=start + len(value),
        confidence=0.9,
        source="regex",
        severity="medium",
    )


def test_overlapping_entities_leave_no_fragment() -> None:
    text = "Contact Mariam Al-Example now"
    entities = [
        _entity("PERSON", text, "Mariam Al-Example"),
        _entity("PERSON", text, "Al-Example now"),
    ]
    assert redact(text, entities).safe_text == "Contact [PERSON_1]"


def test_redaction_preserves_arabic_and_punctuation() -> None:
    text = "البريد: a@example.com، شكرًا"
    result = redact(text, [_entity("EMAIL", text, "a@example.com")])
    assert result.safe_text == "البريد: [EMAIL_1]، شكرًا"


def test_entity_offsets_select_exact_values() -> None:
    result = inspect_and_process(text=CONTRACT)
    assert result["analysis"]["entities"]
    for entity in result["analysis"]["entities"]:
        assert CONTRACT[entity["start"] : entity["end"]] == entity["value"]
