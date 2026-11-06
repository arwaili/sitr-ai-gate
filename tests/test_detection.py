import json
import re
import time
from collections import Counter
from pathlib import Path

import pytest

from data.generate_dataset import (
    ACTION_RISK,
    STATIC_CARRIERS,
    build_examples,
    dataset_card,
    is_safe_carrier,
    migrate_phones,
)
from src import hf_detection, risk_classifier
from src.hf_detection import decode, detect_entities
from src.risk_classifier import classify_risk

EXAMPLES = build_examples()


def test_dataset_is_reproducible_and_unique() -> None:
    assert build_examples() == EXAMPLES
    assert len({example["text"] for example in EXAMPLES}) == len(EXAMPLES) == 300


def test_dataset_is_balanced_with_a_stratified_test_split() -> None:
    counts = Counter((e["expected_action"], e["language"]) for e in EXAMPLES)
    assert set(counts.values()) == {25}
    test = Counter((e["expected_action"], e["language"]) for e in EXAMPLES if e["split"] == "test")
    assert set(test.values()) == {5}
    assert all(ACTION_RISK[e["expected_action"]] == e["expected_risk"] for e in EXAMPLES)


def test_dataset_offsets_select_exact_values() -> None:
    for example in EXAMPLES:
        for entity in example["entities"]:
            assert example["text"][entity["start"] : entity["end"]] == entity["value"]


def test_dataset_values_are_visibly_synthetic() -> None:
    for entity in (entity for example in EXAMPLES for entity in example["entities"]):
        value, kind = entity["value"], entity["entity_type"]
        if kind == "EMAIL":
            assert value.endswith("@example.com")
        elif kind == "IBAN":
            assert value.startswith("QA00SYNT")
        elif kind == "API_KEY":
            assert value.startswith("sk-synthetic-")
        elif kind in {"PASSWORD", "DATABASE_URL"}:
            assert "ynthetic" in value


def test_low_risk_examples_contain_no_entities() -> None:
    for example in EXAMPLES:
        assert bool(example["entities"]) == (example["expected_action"] != "allow")


def test_committed_dev_split_is_valid() -> None:
    rows = json.loads(Path("data/synthetic_examples.json").read_text(encoding="utf-8"))
    assert rows and all(row["split"] == "dev" for row in rows)
    for row in rows:
        for entity in row["entities"]:
            assert row["text"][entity["start"] : entity["end"]] == entity["value"]


@pytest.mark.parametrize("language", ["en", "ar"])
def test_static_carriers_pass_the_safety_filter(language: str) -> None:
    assert all(is_safe_carrier(text, language) for text in STATIC_CARRIERS[language])


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Call us on 5555 today for a great offer.", "en"),
        ("Email the team at info@example.com for details.", "en"),
        ("Use the key sk-abc to unlock our new menu.", "en"),
        ("Review the employment contract before Sunday.", "en"),
        ("اقرأ عقد العمل قبل يوم الأحد من فضلك.", "ar"),
        ("استمتع بالقهوة في Doha هذا المساء.", "ar"),
        ("Short.", "en"),
        ("نقدم لكم خدمات نقل جديدة تلبي احتياجاتكم في أقصى便利!", "ar"),
        ("Learn photography in our free workshop! #PhotographyBeginners", "en"),
        ("استمتع بتجربة عائلية مميزة في الحديقة العامة مع الألعاب", "ar"),
        ('توفير الراحة الكاملة في رحلات التنقل العامة".', "ar"),
    ],
)
def test_safety_filter_rejects_unsafe_carriers(text: str, language: str) -> None:
    assert not is_safe_carrier(text, language)


def test_model_written_carriers_are_marked() -> None:
    carriers = {
        "en": STATIC_CARRIERS["en"] + ["Taste our new mango juice at the harbor stand."],
        "ar": STATIC_CARRIERS["ar"] + ["تذوق عصير المانجو الجديد في كشك الميناء."],
    }
    examples = build_examples(carriers=carriers)
    marked = [e for e in examples if e["carrier_source"] == "qwen"]
    assert marked and all("المانجو" in e["text"] or "mango" in e["text"] for e in marked)


def test_dataset_card_lists_every_split() -> None:
    card = dataset_card(EXAMPLES)
    assert re.search(r"\| test \| block \| ar \| 5 \|", card)
    assert "path: data/dev.jsonl" in card


def test_dataset_phones_cannot_belong_to_real_people() -> None:
    phones = [e["value"] for x in EXAMPLES for e in x["entities"] if e["entity_type"] == "PHONE"]
    assert phones and all(p.startswith("+974 0000 ") for p in phones)


def test_phone_migration_keeps_offsets_exact() -> None:
    old = [{"text": "Call +974 5555 0107 now", "entities": [
        {"entity_type": "PHONE", "value": "+974 5555 0107", "start": 5, "end": 19}]}]
    [row] = migrate_phones(old)
    assert row["text"] == "Call +974 0000 0107 now"
    assert row["entities"][0]["value"] == "+974 0000 0107"


def test_committed_dev_split_uses_safe_phones() -> None:
    assert "+974 5555" not in Path("data/synthetic_examples.json").read_text(encoding="utf-8")


# PII detector: decoding and fallback (no model needed)


def test_decode_joins_names_and_grows_partial_words() -> None:
    text = "Name: Lina Aziz, لينا"
    offsets = [(0, 5), (5, 10), (10, 15), (15, 16), (16, 18), (18, 21)]
    labels = ["O", "B-FIRSTNAME", "S-LASTNAME", "O", "O", "S-FIRSTNAME"]
    entities = decode(text, offsets, labels, [0.1, 0.9, 0.8, 0.1, 0.1, 0.9])
    assert [e.value for e in entities] == ["Lina Aziz", "لينا"]
    assert {e.entity_type for e in entities} == {"PERSON"}
    assert all(text[e.start : e.end] == e.value for e in entities)
    assert entities[0].source == "hf_ner" and entities[0].confidence == 0.8


def test_decode_drops_low_confidence_and_implausible_spans() -> None:
    text = "port 5432 and Sara"
    labels = ["O", "S-EMAIL", "O", "S-FIRSTNAME"]
    offsets = [(0, 4), (4, 9), (9, 13), (13, 18)]
    assert decode(text, offsets, labels, [0.1, 0.99, 0.1, 0.4]) == []


def test_decode_ignores_unmapped_labels() -> None:
    assert decode("Doha", [(0, 4)], ["S-CITY"], [0.99]) == []


def test_detector_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("SITR_HF_MODELS", "0")
    assert detect_entities("Sara Haddad") == []
    assert hf_detection.status()["state"] == "disabled"


def test_detector_failure_falls_back_to_no_findings(monkeypatch) -> None:
    def broken(_text):
        raise RuntimeError("synthetic failure mentioning Sara Haddad")

    monkeypatch.setattr(hf_detection, "_predict", broken)
    assert detect_entities("Sara Haddad") == []
    assert hf_detection.status() == {
        "model": hf_detection.MODEL_ID, "state": "unavailable", "detail": "RuntimeError"
    }


def test_detector_timeout_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(hf_detection, "TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(hf_detection, "_predict", lambda _text: time.sleep(0.5) or [])
    assert detect_entities("Sara Haddad") == []
    assert "timed out" in hf_detection.status()["detail"]
    time.sleep(0.5)  # let the slow call finish before other tests use the worker


def test_require_entities_raises_without_leaking_input(monkeypatch) -> None:
    def broken(_text):
        raise RuntimeError("synthetic failure mentioning Sara Haddad")

    monkeypatch.setattr(hf_detection, "_predict", broken)
    with pytest.raises(hf_detection.DetectorUnavailable) as caught:
        hf_detection.require_entities("Sara Haddad")
    assert "Sara" not in str(caught.value)


def test_status_returns_to_ready_after_a_failure(monkeypatch) -> None:
    monkeypatch.setattr(hf_detection, "_predict", lambda _text: 1 / 0)
    assert detect_entities("Sara Haddad") == []
    monkeypatch.setattr(hf_detection, "_predict", lambda _text: [])
    assert detect_entities("Sara Haddad") == []
    assert hf_detection.status()["state"] == "ready"


# Risk classifier: fallback (no model needed)


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("Employment contract", "high"),
        ("عقد عمل", "high"),
        ("The database password is below", "critical"),
        ("A public slogan", "low"),
    ],
)
def test_fallback_risk_levels(monkeypatch, text: str, level: str) -> None:
    monkeypatch.setenv("SITR_HF_MODELS", "0")
    prediction = classify_risk(text)
    assert prediction.risk_level == level
    assert 0 <= prediction.confidence <= 1
    assert prediction.explanation.startswith("Fallback")


def test_classifier_failure_uses_fallback(monkeypatch) -> None:
    def broken(_text):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(risk_classifier, "_predict", broken)
    assert classify_risk("Employment contract").risk_level == "high"
    assert risk_classifier.status()["state"] == "unavailable"


# Real models: run locally when torch and the cached models are present, skipped in CI


def _cached(model_id: str) -> bool:
    try:
        import torch  # noqa: F401
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(model_id, "config.json"), str)


needs_pii_model = pytest.mark.skipif(
    not _cached(hf_detection.MODEL_ID), reason="PII model not installed"
)
needs_risk_model = pytest.mark.skipif(
    not _cached(risk_classifier.MODEL_ID), reason="risk model not installed"
)


@needs_pii_model
@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Applicant / المتقدم: Mariam Al-Example.", "Mariam Al-Example"),
        ("لخّص هذه السيرة الذاتية. الاسم: لينا الناصر، البريد staff12@example.com", "لينا الناصر"),
    ],
)
def test_model_finds_names_with_exact_offsets(text: str, name: str) -> None:
    people = [e for e in detect_entities(text) if e.entity_type == "PERSON"]
    assert [e.value for e in people] == [name]
    assert all(text[e.start : e.end] == e.value for e in people)


@needs_pii_model
def test_model_finds_nothing_in_public_text() -> None:
    assert detect_entities("Public notice إعلان عام about the new metro line.") == []


@needs_risk_model
@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("Write a short announcement for our new cafe opening in Doha.", "low"),
        ("Summarize this CV. Email: staff7@example.com, phone +974 0000 0107.", "medium"),
        ("Employment contract: monthly salary 25,000 QAR, confidential.", "high"),
        ('DB_PASSWORD = "Synthetic-Pass-01"\nAPI_KEY = "sk-synthetic-0000"', "critical"),
    ],
)
def test_model_risk_levels_for_the_demo_scenarios(text: str, level: str) -> None:
    prediction = classify_risk(text)
    assert prediction.risk_level == level
    assert not prediction.explanation.startswith("Fallback")


@needs_pii_model
def test_ai_product_names_are_not_people() -> None:
    # Regression (R1): "Claude" in "can I upload this to Claude?" was found as a name.
    people = [e for e in detect_entities("Can I upload this contract to Claude or ChatGPT?")
              if e.entity_type == "PERSON"]
    assert people == []


def _finding(entity_type: str, value: str):
    from src.contracts import SensitiveEntity

    return SensitiveEntity(entity_type=entity_type, value=value, start=0, end=len(value),
                           confidence=0.9, source="hf_ner", severity="medium")


@pytest.mark.parametrize("value", ["hello", "Hello!", "thank you", "مرحبا", "السلام عليكم"])
def test_greetings_are_not_usernames_or_names(value: str) -> None:
    # Regression: the model read a lone "hello" as a username, so small talk got a verdict.
    for kind in ("USERNAME", "PERSON"):
        assert not hf_detection._plausible(_finding(kind, value))


def test_real_usernames_and_names_are_kept() -> None:
    assert hf_detection._plausible(_finding("USERNAME", "test.applicant01"))
    assert hf_detection._plausible(_finding("PERSON", "Mariam Al-Example"))


@needs_pii_model
def test_a_greeting_has_no_findings() -> None:
    assert detect_entities("hello") == []
