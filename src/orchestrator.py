"""Lane 3 mock of the single public entry point.

The signature and response schema are final. The detection, policy, and routing inside are
placeholders, self-contained so Lane 4 can build the interface before Lanes 1 and 2 merge.
"""

import re
import time
import uuid
from pathlib import Path

from src.contracts import (
    AnalysisResult,
    FinalResponse,
    ModelMetadata,
    RedactionResult,
    Replacement,
    SensitiveEntity,
)

_METADATA = ModelMetadata(detector="mock-rules-v0", classifier="mock-keywords-v0")

_PATTERNS = [
    ("API_KEY", r"\bsk-[A-Za-z0-9_-]{8,}", "critical", "secret_scanner"),
    ("EMAIL", r"[\w.+-]+@[\w-]+\.[\w.-]+", "medium", "regex"),
    ("PHONE", r"\+974[ -]?\d{4}[ -]?\d{4}", "medium", "regex"),
    ("QATAR_ID", r"\b\d{11}\b", "high", "regex"),
]
_CONFIDENTIAL_TERMS = ("contract", "salary", "evaluation", "عقد", "راتب", "تقييم")

_DECISIONS = {
    "block": (
        "critical",
        95,
        ["ACTIVE_CREDENTIAL"],
        "A credential was found, so nothing was sent to any model.",
    ),
    "private": (
        "high",
        70,
        ["CONFIDENTIAL_CONTENT"],
        "Confidential business content was found, so only the private route may process it.",
    ),
    "redact": (
        "medium",
        40,
        ["PERSONAL_DATA"],
        "Personal data was found and replaced with placeholders before processing.",
    ),
    "allow": ("low", 5, [], "No sensitive content was found."),
}

_MOCK_RESPONSES = {
    "allow": "[Mock approved model] A {intent} response would appear here.",
    "redact": "[Mock approved model] A {intent} of the sanitized text would appear here.",
    "private": "[Mock private model] A {intent} from the private route would appear here.",
}


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


def _decide(text: str, entities: list[SensitiveEntity]) -> str:
    severities = {entity.severity for entity in entities}
    if "critical" in severities:
        return "block"
    lowered = text.lower()
    if "high" in severities or any(term in lowered for term in _CONFIDENTIAL_TERMS):
        return "private"
    return "redact" if severities else "allow"


def _redact(text: str, entities: list[SensitiveEntity]) -> RedactionResult:
    placeholders: dict[str, str] = {}
    replacements: list[Replacement] = []
    parts: list[str] = []
    cursor = 0
    for entity in entities:
        if entity.value not in placeholders:
            prefix = f"[{entity.entity_type}_"
            count = sum(placeholder.startswith(prefix) for placeholder in placeholders.values())
            placeholders[entity.value] = f"{prefix}{count + 1}]"
            replacements.append(
                Replacement(
                    placeholder=placeholders[entity.value],
                    entity_type=entity.entity_type,
                    original_value=entity.value,
                )
            )
        parts += [text[cursor : entity.start], placeholders[entity.value]]
        cursor = entity.end
    parts.append(text[cursor:])
    return RedactionResult(original_text=text, safe_text="".join(parts), replacements=replacements)


def _read_file(file_path: str) -> str:
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # shortcut: PDFs and images end here, replace with ingest() at Checkpoint C
        raise ValueError("This file could not be read as text.") from exc


def _error(message: str, started: float) -> dict:
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
        latency_ms=int((time.perf_counter() - started) * 1000),
    ).model_dump()


def inspect_and_process(
    text: str | None = None,
    file_path: str | None = None,
    user_intent: str = "summarize",
) -> dict:
    """Inspect one input and return the frozen FinalResponse schema as a dict."""
    started = time.perf_counter()
    try:
        content = _read_file(file_path) if file_path else text
    except ValueError as exc:
        return _error(str(exc), started)
    if not content or not content.strip():
        return _error("No readable content was provided.", started)

    entities = _detect(content)
    action = _decide(content, entities)
    risk_level, risk_score, reason_codes, explanation = _DECISIONS[action]
    model_response = None
    if action != "block":
        model_response = _MOCK_RESPONSES[action].format(intent=user_intent)
    return FinalResponse(
        status="blocked" if action == "block" else "completed",
        action_taken=action,
        analysis=AnalysisResult(
            document_id=str(uuid.uuid4()),
            entities=entities,
            risk_level=risk_level,
            risk_score=risk_score,
            recommended_action=action,
            reason_codes=reason_codes,
            explanation=explanation,
            model_metadata=_METADATA,
        ),
        redaction=_redact(content, entities),
        model_response=model_response,
        user_message=explanation,
        latency_ms=int((time.perf_counter() - started) * 1000),
    ).model_dump()
