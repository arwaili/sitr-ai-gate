"""Deterministic policy: findings decide the action, and rules always beat model guesses.

Overrides, strictest first (PROJECT_OVERVIEW.md, Phase 5):
- A credential or private key found by the rules -> critical/block.
- Restricted operational information (internal hosts, "restricted" markings) -> critical/block.
- Confidential HR or financial content -> high/private. This includes high-severity findings,
  confidential terms, a credential suspected only by the model, and the semantic classifier.
- Ordinary contact details -> medium/redact.
- Nothing found -> low/allow.
Models can raise a decision to private at most; only rules can block or lower it.
"""

from src.contracts import Action, AnalysisResult, ModelMetadata, SensitiveEntity

_CONFIDENTIAL_TERMS = (
    "contract", "salary", "payroll", "evaluation", "appraisal", "confidential", "termination",
    "عقد", "راتب", "رواتب", "تقييم", "سري", "إنهاء الخدمة",
)
_RESTRICTED_TERMS = (
    "top secret", "classification: restricted", "restricted information", "internal use only",
    "do not distribute",
    "سري للغاية", "مقيد", "للاستخدام الداخلي فقط",
)
_CREDENTIAL_CODES = {
    "API_KEY": "ACTIVE_CREDENTIAL",
    "CLOUD_KEY": "ACTIVE_CREDENTIAL",
    "BEARER_TOKEN": "ACTIVE_CREDENTIAL",
    "JWT": "ACTIVE_CREDENTIAL",
    "PASSWORD": "PASSWORD",
    "DATABASE_URL": "DATABASE_CREDENTIAL",
    "PRIVATE_KEY": "PRIVATE_KEY",
}
# The classifier may route to private only when it is this sure; tuned on the dev split.
SEMANTIC_THRESHOLD = 0.6

_DECISIONS = {
    "block": ("critical", 95, "Restricted content was found, so nothing was sent to any model."),
    "private": (
        "high",
        70,
        "Confidential content was found, so only the private route may process it.",
    ),
    "redact": (
        "medium",
        40,
        "Personal data was found and replaced with placeholders before processing.",
    ),
    "allow": ("low", 5, "No sensitive content was found."),
}
_BLOCK_MESSAGES = {
    "ACTIVE_CREDENTIAL": "A credential was found, so nothing was sent to any model.",
    "PASSWORD": "A password was found, so nothing was sent to any model.",
    "DATABASE_CREDENTIAL": "A database credential was found, so nothing was sent to any model.",
    "PRIVATE_KEY": "A private key was found, so nothing was sent to any model.",
}


def merge_findings(
    rules: list[SensitiveEntity], model: list[SensitiveEntity]
) -> list[SensitiveEntity]:
    """Rules first; a model finding is kept only where no rule finding overlaps it."""
    kept = [m for m in model if not any(r.start < m.end and m.start < r.end for r in rules)]
    return sorted(rules + kept, key=lambda entity: (entity.start, -entity.end))


def _assess(text: str, entities: list[SensitiveEntity], semantic) -> tuple[Action, list[str]]:
    rules = [e for e in entities if e.source != "hf_ner"]
    lowered = text.lower()

    block = sorted({_CREDENTIAL_CODES[e.entity_type] for e in rules
                    if e.severity == "critical" and e.entity_type in _CREDENTIAL_CODES})
    if any(e.entity_type == "INTERNAL_HOST" for e in rules) or any(
        term in lowered for term in _RESTRICTED_TERMS
    ):
        block.append("RESTRICTED_OPERATIONAL")
    if any(e.severity == "critical" and e.entity_type not in _CREDENTIAL_CODES for e in rules):
        block.append("CRITICAL_FINDING")
    if block:
        return "block", block

    private = []
    if any(e.severity == "high" for e in entities):
        private.append("CONFIDENTIAL_DATA")
    if any(e.severity == "critical" for e in entities):
        # Only the model saw it: suspicious, but not proof, so keep it off external routes.
        private.append("MODEL_SUSPECTED_CREDENTIAL")
    if any(term in lowered for term in _CONFIDENTIAL_TERMS):
        private.append("CONFIDENTIAL_CONTENT")
    if (
        semantic is not None
        and semantic.risk_level == "high"
        and semantic.confidence >= SEMANTIC_THRESHOLD
    ):
        private.append("SEMANTIC_HIGH_RISK")
    if private:
        return "private", private

    if entities:
        return "redact", ["PERSONAL_DATA"]
    return "allow", []


def decide(
    document_id: str,
    text: str,
    entities: list[SensitiveEntity],
    metadata: ModelMetadata,
    semantic=None,
) -> AnalysisResult:
    """Return the analysis with the strictest action the findings require.

    `semantic` is an optional `RiskPrediction` from `src.risk_classifier.classify_risk`.
    """
    action, reason_codes = _assess(text, entities, semantic)
    risk_level, risk_score, explanation = _DECISIONS[action]
    if action == "block":
        explanation = _BLOCK_MESSAGES.get(reason_codes[0], explanation)
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
