import json
import re
from collections import Counter
from pathlib import Path

import pytest

from data.generate_dataset import (
    ACTION_RISK,
    STATIC_CARRIERS,
    build_examples,
    dataset_card,
    is_safe_carrier,
)
from src.hf_detection import detect_entities
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
