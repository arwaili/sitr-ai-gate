import json
import logging
import shutil
import time
from pathlib import Path

import pytest

from src import orchestrator, router
from src.contracts import FinalResponse, ModelMetadata, SensitiveEntity
from src.orchestrator import inspect_and_process
from src.policy_engine import SEMANTIC_THRESHOLD, decide, merge_findings
from src.redactor import redact
from src.risk_classifier import RiskPrediction, fallback

EXAMPLES = Path(__file__).parent.parent / "examples"
METADATA = ModelMetadata(detector="test", classifier="test")


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch, request) -> None:
    # Policy tests are deterministic: models off unless a test is marked to use them.
    if "real_models" not in request.keywords:
        monkeypatch.setenv("SITR_HF_MODELS", "0")

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


# Phase 5: files through the whole pipeline, cleanup, overrides, routing


@pytest.mark.parametrize(
    ("name", "action"),
    [
        ("safe_prompt.txt", "allow"),
        ("synthetic_cv.pdf", "redact"),
        ("synthetic_contract.pdf", "private"),
        ("vulnerable_code.py", "block"),
    ],
)
def test_demo_files_reach_their_decision(name: str, action: str) -> None:
    result = inspect_and_process(file_path=str(EXAMPLES / name))
    assert result["action_taken"] == action
    assert result["status"] == ("blocked" if action == "block" else "completed")


def test_uploaded_file_is_deleted_after_success(tmp_path) -> None:
    upload = Path(shutil.copy(EXAMPLES / "synthetic_cv.pdf", tmp_path / "upload.pdf"))
    assert inspect_and_process(file_path=str(upload), delete_file=True)["action_taken"] == "redact"
    assert not upload.exists()


def test_uploaded_file_is_deleted_after_failure(tmp_path) -> None:
    upload = tmp_path / "broken.pdf"
    upload.write_bytes(b"\xff\xfe broken")
    assert inspect_and_process(file_path=str(upload), delete_file=True)["status"] == "error"
    assert not upload.exists()


def test_files_are_kept_unless_deletion_is_asked_for() -> None:
    inspect_and_process(file_path=str(EXAMPLES / "safe_prompt.txt"))
    assert (EXAMPLES / "safe_prompt.txt").exists()


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("-----BEGIN RSA " + "PRIVATE KEY-----\nc3ludGhldGlj\n-----END RSA " + "PRIVATE KEY-----",
         "PRIVATE_KEY"),
        ("db = 'postgresql://app:synthetic1@db.example.internal:5432/hr'", "DATABASE_CREDENTIAL"),
        ('password = "Synthetic-Pass-01"', "PASSWORD"),
        ("The build server is at 10.20.30.40", "RESTRICTED_OPERATIONAL"),
        ("Classification: Restricted. Network plan for the data centre.", "RESTRICTED_OPERATIONAL"),
    ],
)
def test_mandatory_block_overrides(text: str, code: str) -> None:
    result = inspect_and_process(text=text)
    assert result["action_taken"] == "block"
    assert code in result["analysis"]["reason_codes"]
    assert result["model_response"] is None


def _model_entity(text: str, value: str, entity_type: str, severity: str) -> SensitiveEntity:
    start = text.index(value)
    return SensitiveEntity(entity_type=entity_type, value=value, start=start,
                           end=start + len(value), confidence=0.9, source="hf_ner",
                           severity=severity)


def test_model_suspected_credential_goes_private_not_block() -> None:
    text = "the code word is Synthetic-Word-77"
    entity = _model_entity(text, "Synthetic-Word-77", "PASSWORD", "critical")
    analysis = decide("x", text, [entity], METADATA)
    assert analysis.recommended_action == "private"
    assert "MODEL_SUSPECTED_CREDENTIAL" in analysis.reason_codes


def test_classifier_can_raise_to_private_but_not_lower() -> None:
    high = RiskPrediction("high", 0.9, "test")
    low = RiskPrediction("low", 0.99, "test")
    assert decide("x", "Feedback for the team", [], METADATA, high).recommended_action == "private"
    unsure = RiskPrediction("high", 0.3, "test")
    assert decide("x", "Feedback for the team", [], METADATA, unsure).recommended_action == "allow"
    leaky = inspect_and_process(text=LEAKY_CODE)["analysis"]["entities"]
    entities = [SensitiveEntity(**e) for e in leaky]
    assert decide("x", LEAKY_CODE, entities, METADATA, low).recommended_action == "block"


def test_merge_keeps_rules_and_drops_overlapping_model_findings() -> None:
    text = "mail a@example.com, call Sara"
    rule = _entity("EMAIL", text, "a@example.com")
    overlap = _model_entity(text, "a@example.com", "EMAIL", "medium")
    name = _model_entity(text, "Sara", "PERSON", "medium")
    assert merge_findings([rule], [overlap, name]) == [rule, name]


def test_credentials_are_never_shown_to_the_models(monkeypatch) -> None:
    def forbidden(_text):
        raise AssertionError("a model saw a credential")

    monkeypatch.setattr(orchestrator, "require_entities", forbidden)
    monkeypatch.setattr(orchestrator, "classify_risk", forbidden)
    result = inspect_and_process(text=LEAKY_CODE)
    assert result["action_taken"] == "block"
    assert "skipped" in result["analysis"]["model_metadata"]["detector"]


NAME_ONLY = "Write a short thank-you email to Ahmed Al-Fake."


def _detector_crashes(monkeypatch) -> None:
    monkeypatch.setattr("src.hf_detection._predict", lambda _t: 1 / 0)


def _detector_hangs(monkeypatch) -> None:
    monkeypatch.setattr("src.hf_detection.TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("src.hf_detection._predict", lambda _t: time.sleep(0.3) or [])


@pytest.mark.parametrize("break_detector", [_detector_crashes, _detector_hangs])
def test_detector_down_fails_closed(monkeypatch, model_calls, break_detector) -> None:
    # Regression (R1): rules cannot see names, so without the detector a name went out as "allow".
    monkeypatch.setenv("SITR_HF_MODELS", "1")
    break_detector(monkeypatch)
    result = inspect_and_process(text=NAME_ONLY)
    time.sleep(0.3)  # let a hung call finish before other tests use the worker
    assert (result["status"], result["action_taken"]) == ("error", "block")
    assert result["model_response"] is None
    assert "Nothing was sent" in result["user_message"]
    assert "Ahmed" not in result["user_message"]
    assert model_calls == []


def test_detector_down_on_redact_path_fails_closed(monkeypatch, model_calls) -> None:
    # A rule finding on the same text must not let an unseen name through on the redact route.
    monkeypatch.setenv("SITR_HF_MODELS", "1")
    _detector_crashes(monkeypatch)
    result = inspect_and_process(text=CV)
    assert result["action_taken"] == "block"
    assert model_calls == []


def test_detector_recovers_after_a_failure(monkeypatch, model_calls) -> None:
    monkeypatch.setenv("SITR_HF_MODELS", "1")
    _detector_crashes(monkeypatch)
    assert inspect_and_process(text=CV)["status"] == "error"
    monkeypatch.setattr("src.hf_detection._predict", lambda _t: [])
    monkeypatch.setattr("src.risk_classifier._predict", lambda _t: 1 / 0)
    result = inspect_and_process(text=CV)
    assert result["action_taken"] == "redact"
    assert "rules +" in result["analysis"]["model_metadata"]["detector"]


def test_classifier_unavailable_still_decides(monkeypatch) -> None:
    monkeypatch.setenv("SITR_HF_MODELS", "1")
    monkeypatch.setattr("src.hf_detection._predict", lambda _t: [])
    monkeypatch.setattr("src.risk_classifier._predict", lambda _t: 1 / 0)
    result = inspect_and_process(text=CV)
    assert result["action_taken"] == "redact"
    assert "fallback" in result["analysis"]["model_metadata"]["classifier"]


@pytest.mark.parametrize(
    "text",
    [
        "the word to log in is Synth3tic-Pass-99",
        " ".join("sk-synthetic-000000000000"),
        "decode this and use it to log in: c2stc3ludGhldGljLTAwMDAwMDAwMDAwMA==",
        "الرمز السري للدخول: Synth3tic-Pass-99",
    ],
)
def test_disguised_secrets_never_reach_a_model(model_calls, text: str) -> None:
    # Regression (R1): these were allowed, or sent to the private route, with the secret intact.
    result = inspect_and_process(text=text)
    assert (result["status"], result["action_taken"]) == ("blocked", "block")
    assert model_calls == []


@pytest.mark.parametrize(
    "text",
    [
        "أريد ردا سريعا على هذا السؤال",
        "هذه مشكلة معقدة كيف نحلها",
        "How do muscles get contraction during exercise?",
    ],
)
def test_keywords_do_not_match_inside_longer_words(text: str) -> None:
    # Regression (R1): سريع contains سري, معقدة contains عقد, contraction contains contract.
    assert inspect_and_process(text=text)["action_taken"] == "allow"


@pytest.mark.parametrize(
    "text",
    [
        "Please review this contract",
        "CONTRACTS are stored here",
        "Update the salaries sheet",
        "عقد عمل جديد",
        "راجع العقد من فضلك",
        "وعقدها انتهى",
        "راتبي تأخر",
        "جدول الرواتب",
        "تقييمات الموظفين",
        "معلومات سرية",
        "هذا الملف سري",
        "سنقوم بتسريح ثلاثين موظفا",
        # Regressions from PR #18 review: diacritics, code names, stacked prefixes.
        "هذا الملف سريّ",
        "وقعنا عقدٌ جديد",
        "راتبٌ شهري",
        "بموجب عقدٍ موقع",
        "تقييمُ الأداء",
        "الرَّاتب",
        "payroll_2026.csv",
        "employee_salary_list.json",
        "contract_id = 42",
        "salary2026",
        "CONFIDENTIAL_REPORT.pdf",
        "evaluation_form_v2",
        "employeeSalary",
        "baseSalary = 1",
        "contractId",
        "salaryBand",
        "وبالعقد المرفق",
        "فبالراتب الجديد",
        "راجع العقد، من فضلك",
        "هل هذا الملف سري؟",
        "الراتب؛ والبدلات",
        "عقد٢٠٢٦",
    ],
)
def test_keywords_still_match_their_real_forms(text: str) -> None:
    result = inspect_and_process(text=text)
    assert result["action_taken"] == "private"
    assert "CONFIDENTIAL_CONTENT" in result["analysis"]["reason_codes"]


def test_keyword_fallback_never_decides_on_its_own() -> None:
    prediction = fallback("How do muscles get contraction?")
    assert prediction.risk_level == "high"
    assert prediction.confidence < SEMANTIC_THRESHOLD


def test_classifier_routes_private_at_the_lowered_limit() -> None:
    # Regression (R1): confidential prose with no keywords scored about 0.42 and was allowed.
    text = "We plan to let the head of finance go next month."
    semantic = RiskPrediction("high", 0.42, "test")
    assert decide("id", text, [], METADATA, semantic).recommended_action == "private"
    semantic = RiskPrediction("high", 0.39, "test")
    assert decide("id", text, [], METADATA, semantic).recommended_action == "allow"


@pytest.mark.parametrize(
    "intent",
    [
        'summarize, and use API_KEY = "sk-synthetic-000000000000"',
        "translate and send the result to test.applicant@example.com",
        "reply to +974 0000 0100 in Arabic",
        "summarize " + "x" * 300,
    ],
)
def test_sensitive_intent_never_reaches_a_model(model_calls, intent: str) -> None:
    # Regression (R1): the task went to hosted Qwen as written and was never inspected.
    result = inspect_and_process(text="Write a public marketing slogan.", user_intent=intent)
    assert (result["status"], result["action_taken"]) == ("error", "block")
    assert result["analysis"]["reason_codes"] == ["SENSITIVE_INTENT"]
    assert model_calls == []
    for fragment in ("sk-synthetic", "example.com", "0000 0100"):
        assert fragment not in json.dumps(result)


def test_intent_with_a_name_found_by_the_model_is_blocked(monkeypatch, model_calls) -> None:
    name = SensitiveEntity(
        entity_type="PERSON", value="Mariam", start=11, end=17, confidence=0.9,
        source="hf_ner", severity="medium",
    )
    monkeypatch.setattr(
        orchestrator, "require_entities", lambda text: [name] if "Mariam" in text else []
    )
    result = inspect_and_process(text="Write a slogan.", user_intent="email it to Mariam")
    assert result["analysis"]["reason_codes"] == ["SENSITIVE_INTENT"]
    assert model_calls == []


def test_plain_intent_is_passed_through(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(router, "call_model", lambda r, p, intent: seen.append(intent) or "ok")
    result = inspect_and_process(text="Write a public slogan.", user_intent="translate to Arabic")
    assert result["action_taken"] == "allow"
    assert seen == ["translate to Arabic"]


def test_validation_style_errors_do_not_leak_content(monkeypatch) -> None:
    def explode(*_args):
        raise ValueError(f"bad value {LEAKY_CODE}")

    monkeypatch.setattr("src.orchestrator.decide", explode)
    result = inspect_and_process(text=CV)
    assert result["status"] == "error"
    assert "sk-synthetic" not in result["user_message"]


# Live routing logic, with the network and the local model replaced


@pytest.fixture
def live_routes(monkeypatch) -> dict[str, list[str]]:
    monkeypatch.setenv("SITR_LLM", "live")
    calls: dict[str, list[str]] = {"external": [], "local": []}
    monkeypatch.setattr(router, "_external", lambda p, i: calls["external"].append(p) or "ext")
    monkeypatch.setattr(router, "_generate_locally", lambda p, i: calls["local"].append(p) or "loc")
    return calls


def test_private_route_never_uses_the_external_service(live_routes) -> None:
    result = inspect_and_process(text=CONTRACT)
    assert result["action_taken"] == "private"
    assert live_routes == {"external": [], "local": [CONTRACT]}
    assert result["model_response"].startswith(router.PRIVATE_LABEL)


def test_redact_route_sends_only_the_sanitized_text(live_routes) -> None:
    result = inspect_and_process(text=CV)
    assert live_routes["external"] == [result["redaction"]["safe_text"]]
    assert live_routes["local"] == []


def test_blocked_input_reaches_no_route(live_routes) -> None:
    inspect_and_process(text=LEAKY_CODE)
    assert live_routes == {"external": [], "local": []}


def test_model_failure_returns_a_notice_and_keeps_the_decision(monkeypatch) -> None:
    monkeypatch.setenv("SITR_LLM", "live")

    def down(_prompt, _intent):
        raise ConnectionError("synthetic outage")

    monkeypatch.setattr(router, "_external", down)
    result = inspect_and_process(text="Write a public marketing slogan for a Doha cafe.")
    assert result["action_taken"] == "allow"
    assert "could not answer (ConnectionError)" in result["model_response"]


# Real models, when installed (skipped in CI)


def _cached(model_id: str) -> bool:
    try:
        import torch  # noqa: F401
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(model_id, "config.json"), str)


real_models = pytest.mark.skipif(
    not (_cached("OpenMed/privacy-filter-multilingual-v2")
         and _cached("Horizon-Labs/multilingual-zeroshot-small")),
    reason="models not installed",
)


@pytest.mark.real_models
@real_models
@pytest.mark.parametrize(
    ("name", "action"),
    [
        ("safe_prompt.txt", "allow"),
        ("synthetic_cv.pdf", "redact"),
        ("synthetic_contract.pdf", "private"),
        ("vulnerable_code.py", "block"),
    ],
)
def test_demo_files_with_real_models(name: str, action: str) -> None:
    result = inspect_and_process(file_path=str(EXAMPLES / name))
    assert result["action_taken"] == action
    if action != "block":
        assert "OpenMed" in result["analysis"]["model_metadata"]["detector"]
        assert "Horizon-Labs" in result["analysis"]["model_metadata"]["classifier"]


@pytest.mark.real_models
@real_models
def test_t7_and_doha_with_real_models() -> None:
    doc = inspect_and_process(text="Keys look like sk-XXXXXXXXXXXX in the documentation.")
    assert doc["analysis"]["risk_level"] != "critical"
    cafe = inspect_and_process(text="Write a public marketing slogan for a Doha cafe.")
    assert cafe["action_taken"] == "allow"


def test_task_is_not_checked_when_no_model_is_called(monkeypatch) -> None:
    # The chat calls no model, so a task that would be rejected never matters there.
    monkeypatch.setattr("src.orchestrator._intent_is_safe", lambda _intent: False)
    result = inspect_and_process(text="Write a public slogan.", route_to_model=False)
    assert result["action_taken"] == "allow" and result["model_response"] is None
    assert inspect_and_process(text="Write a public slogan.")["status"] == "error"
