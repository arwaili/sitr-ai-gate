"""The single public entry point: inspect, decide, redact, route, and audit one input."""

import contextlib
import time
import uuid
from pathlib import Path

from src import audit, hf_detection, risk_classifier, router
from src.contracts import AnalysisResult, FinalResponse, ModelMetadata, SensitiveEntity
from src.deterministic import detect_deterministic
from src.hf_detection import DetectorUnavailable, require_entities
from src.ingestion import ingest
from src.policy_engine import decide, merge_findings
from src.redactor import redact
from src.risk_classifier import classify_risk

_ERROR_METADATA = ModelMetadata(detector="not run", classifier="not run")
DETECTOR_DOWN_MESSAGE = "The privacy detector is not ready, so this input was blocked. Try again."
INTENT_MESSAGE = (
    "The intended task contains personal or secret data, so this input was blocked. "
    "Keep the task short and put any details in the prompt."
)
# The task travels to the model as written, so it must be short and contain nothing sensitive.
MAX_INTENT_CHARS = 200


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _error(message: str, started: float, reason: str = "PROCESSING_ERROR") -> FinalResponse:
    # The contract requires an action and risk, and unknown content must fail closed.
    return FinalResponse(
        status="error",
        action_taken="block",
        analysis=AnalysisResult(
            document_id=str(uuid.uuid4()),
            risk_level="critical",
            risk_score=100,
            recommended_action="block",
            reason_codes=[reason],
            explanation=message,
            model_metadata=_ERROR_METADATA,
        ),
        user_message=f"{message} Nothing was sent to any model.",
        latency_ms=_elapsed_ms(started),
    )


def _detect(text: str, pages) -> tuple[list[SensitiveEntity], object, ModelMetadata]:
    rules = detect_deterministic(text, pages)
    if any(e.severity == "critical" for e in rules):
        # A rule already blocks this; the secret is not shown to any model, not even local ones.
        skipped = "skipped: credential found"
        return rules, None, ModelMetadata(detector=f"rules ({skipped})", classifier=skipped)
    entities = merge_findings(rules, require_entities(text))
    semantic = classify_risk(text)
    ner = hf_detection.status()
    detector = (
        f"rules + {hf_detection.MODEL_ID}" if ner["state"] in ("ready", "not loaded")
        else f"rules only ({hf_detection.MODEL_ID} {ner['state']})"
    )
    classifier = (
        f"keyword fallback ({risk_classifier.status()['state']})"
        if semantic.explanation.startswith("Fallback")
        else risk_classifier.MODEL_ID
    )
    return entities, semantic, ModelMetadata(detector=detector, classifier=classifier)


def _intent_is_safe(user_intent: str) -> bool:
    """The task is sent unredacted on every route, so it may hold nothing the gate would catch."""
    if len(user_intent) > MAX_INTENT_CHARS:
        return False
    if detect_deterministic(user_intent):
        # A rule finding is enough; a secret here is never shown to the PII model.
        return False
    return not require_entities(user_intent)


def _process(text: str, pages, user_intent: str, started: float) -> FinalResponse:
    entities, semantic, metadata = _detect(text, pages)
    analysis = decide(str(uuid.uuid4()), text, entities, metadata, semantic)
    action = analysis.recommended_action
    # A blocked input reaches no model, so its task is not inspected (or shown to the PII model).
    if action != "block" and not _intent_is_safe(user_intent):
        return _error(INTENT_MESSAGE, started, reason="SENSITIVE_INTENT")
    redaction = redact(text, entities)
    return FinalResponse(
        status="blocked" if action == "block" else "completed",
        action_taken=action,
        analysis=analysis,
        redaction=redaction,
        model_response=router.route(action, redaction, user_intent),
        user_message=analysis.explanation,
        latency_ms=_elapsed_ms(started),
    )


def inspect_and_process(
    text: str | None = None,
    file_path: str | None = None,
    user_intent: str = "summarize",
    delete_file: bool = False,
) -> dict:
    """Inspect one input and return the frozen FinalResponse schema as a dict.

    Pass `delete_file=True` for uploaded temporary files: the file is removed afterwards,
    whether processing succeeded or failed.
    """
    started = time.perf_counter()
    try:
        try:
            ingestion = ingest(text=text, file_path=file_path)
        except ValueError as exc:
            # Lane 1's ValueErrors carry content-free messages, so they can be shown.
            response = _error(str(exc), started)
        else:
            response = _process(ingestion.text, ingestion.pages, user_intent, started)
    except DetectorUnavailable:
        # Rules cannot see names, so without the detector the text is not known to be safe.
        response = _error(DETECTOR_DOWN_MESSAGE, started)
    except Exception:
        # Any other failure blocks; its text may quote content (pydantic does), so it is dropped.
        response = _error("Sitr could not inspect this input.", started)
    finally:
        if delete_file and file_path:
            with contextlib.suppress(OSError):
                Path(file_path).unlink(missing_ok=True)
    audit.record(response, "file" if file_path else "text")
    return response.model_dump()
