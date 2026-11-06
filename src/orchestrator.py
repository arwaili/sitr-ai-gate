"""The single public entry point: inspect, decide, redact, route, and audit one input.

The signature and response schema are final. Detection is still a self-contained mock so
Lane 4 can build the interface before Lanes 1 and 2 merge.
"""

import re
import time
import uuid
from pathlib import Path

from src import audit, router
from src.contracts import AnalysisResult, FinalResponse, ModelMetadata, SensitiveEntity
from src.policy_engine import decide
from src.redactor import redact

_METADATA = ModelMetadata(detector="mock-rules-v0", classifier="mock-keywords-v0")

# shortcut: mock detection, swap in the Lane 1 and Lane 2 detectors at Checkpoint C
_PATTERNS = [
    ("API_KEY", r"\bsk-[A-Za-z0-9_-]{8,}", "critical", "secret_scanner"),
    ("EMAIL", r"[\w.+-]+@[\w-]+\.[\w.-]+", "medium", "regex"),
    ("PHONE", r"\+974[ -]?\d{4}[ -]?\d{4}", "medium", "regex"),
    ("QATAR_ID", r"\b\d{11}\b", "high", "regex"),
]


def _detect(text: str) -> list[SensitiveEntity]:
    entities = [
        SensitiveEntity(
            entity_type=entity_type,
            value=match.group(),
            start=match.start(),
            end=match.end(),
            confidence=0.99,
            source=source,
            severity=severity,
        )
        for entity_type, pattern, severity, source in _PATTERNS
        for match in re.finditer(pattern, text)
    ]
    return sorted(entities, key=lambda entity: entity.start)


def _read_file(file_path: str) -> str:
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # shortcut: PDFs and images end here, replace with ingest() at Checkpoint C
        raise ValueError("This file could not be read as text.") from exc


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _error(message: str, started: float) -> FinalResponse:
    # The contract requires an action and risk, and unknown content must fail closed.
    return FinalResponse(
        status="error",
        action_taken="block",
        analysis=AnalysisResult(
            document_id=str(uuid.uuid4()),
            risk_level="critical",
            risk_score=100,
            recommended_action="block",
            reason_codes=["PROCESSING_ERROR"],
            explanation=message,
            model_metadata=_METADATA,
        ),
        user_message=f"{message} Nothing was sent to any model.",
        latency_ms=_elapsed_ms(started),
    )


def _process(content: str, user_intent: str, started: float) -> FinalResponse:
    entities = _detect(content)
    analysis = decide(str(uuid.uuid4()), content, entities, _METADATA)
    action = analysis.recommended_action
    redaction = redact(content, entities)
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
) -> dict:
    """Inspect one input and return the frozen FinalResponse schema as a dict."""
    started = time.perf_counter()
    try:
        content = _read_file(file_path) if file_path else text
        if not content or not content.strip():
            raise ValueError("No readable content was provided.")
        response = _process(content, user_intent, started)
    except ValueError as exc:
        response = _error(str(exc), started)
    except Exception:
        # Any unexpected failure blocks; the exception text may contain content, so it is dropped.
        response = _error("Sitr could not inspect this input.", started)
    audit.record(response, "file" if file_path else "text")
    return response.model_dump()
