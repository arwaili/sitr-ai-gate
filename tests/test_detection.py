import pytest

from src.hf_detection import detect_entities
from src.risk_classifier import classify_risk


@pytest.mark.parametrize("name", ["Mariam Al-Example", "مريم المثال"])
def test_names_are_detected_with_exact_offsets(name: str) -> None:
    text = f"Applicant / المتقدم: {name}."
    [entity] = detect_entities(text)
    assert entity.entity_type == "PERSON"
    assert text[entity.start : entity.end] == name


def test_mixed_language_without_names_returns_nothing() -> None:
    assert detect_entities("Public notice إعلان عام") == []


@pytest.mark.parametrize(
    ("text", "level"),
    [("Employment contract", "high"), ("عقد عمل", "high"), ("A public slogan", "low")],
)
def test_classifier_returns_a_contract_risk_level(text: str, level: str) -> None:
    prediction = classify_risk(text)
    assert prediction.risk_level == level
    assert 0 <= prediction.confidence <= 1
    assert prediction.explanation
