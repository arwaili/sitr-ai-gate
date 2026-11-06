"""Deterministic policy: findings decide the action, and rules always beat model guesses."""

from src.contracts import Action, AnalysisResult, ModelMetadata, SensitiveEntity

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


def _action(text: str, entities: list[SensitiveEntity]) -> Action:
    severities = {entity.severity for entity in entities}
    if "critical" in severities:
        return "block"
    lowered = text.lower()
    # shortcut: keyword check stands in for the Lane 2 classifier until Checkpoint C
    if "high" in severities or any(term in lowered for term in _CONFIDENTIAL_TERMS):
        return "private"
    return "redact" if severities else "allow"


def decide(
    document_id: str, text: str, entities: list[SensitiveEntity], metadata: ModelMetadata
) -> AnalysisResult:
    """Return the analysis with the strictest action the findings require."""
    action = _action(text, entities)
    risk_level, risk_score, reason_codes, explanation = _DECISIONS[action]
    return AnalysisResult(
        document_id=document_id,
        entities=entities,
        risk_level=risk_level,
        risk_score=risk_score,
        recommended_action=action,
        reason_codes=reason_codes,
        explanation=explanation,
        model_metadata=metadata,
    )
