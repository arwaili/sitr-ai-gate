"""Lane 2 mock risk classifier. Horizon-Labs/multilingual-zeroshot-small replaces this."""

from typing import NamedTuple

from src.contracts import RiskLevel

_CONFIDENTIAL_TERMS = ("contract", "salary", "evaluation", "عقد", "راتب", "تقييم")


class RiskPrediction(NamedTuple):
    risk_level: RiskLevel
    confidence: float
    explanation: str


def classify_risk(text: str) -> RiskPrediction:
    """Predict semantic risk. Credentials are decided by Lane 3 rules, never by this model."""
    lowered = text.lower()
    if any(term in lowered for term in _CONFIDENTIAL_TERMS):
        return RiskPrediction("high", 0.8, "Mock: the text mentions confidential business terms.")
    return RiskPrediction("low", 0.8, "Mock: no confidential business terms were found.")
