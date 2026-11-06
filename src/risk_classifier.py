"""Lane 2 semantic risk with Horizon-Labs/multilingual-zeroshot-small (zero-shot NLI, CPU).

The model scores the text against one English description per risk level; Arabic text works
with English labels. If the model cannot load or run in time, a keyword fallback answers and
says so in the explanation. Credentials are decided by deterministic rules, never by this
model alone. Set SITR_HF_MODELS=0 to use only the fallback.
"""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import NamedTuple

from src.contracts import RiskLevel

MODEL_ID = "Horizon-Labs/multilingual-zeroshot-small"
TIMEOUT_SECONDS = float(os.environ.get("SITR_MODEL_TIMEOUT", "30"))
HYPOTHESIS = "This text is {}."
# One description per level, tuned on the dev split only.
LABELS: dict[str, RiskLevel] = {
    "a public announcement, marketing text or general question": "low",
    "a request that includes a person's email address or phone number": "medium",
    "a confidential employment contract, salary or performance evaluation": "high",
    "source code or text containing passwords, API keys or secret credentials": "critical",
}
_MAX_CHARS = 4000
# Below the policy's SEMANTIC_THRESHOLD: the policy runs its own keyword check, so the fallback
# is informational and never decides on its own.
_FALLBACK_CONFIDENCE = 0.3

# Substrings are enough here: the fallback sits below the policy limit, so it never decides alone.
# src/policy_engine.py holds the whole-word list that does: change the two together.
_CONFIDENTIAL_TERMS = (
    "contract", "salary", "payroll", "evaluation", "appraisal", "confidential", "termination",
    "عقد", "راتب", "رواتب", "تقييم", "سري", "إنهاء الخدمة",
)
_CREDENTIAL_TERMS = ("password", "api key", "api_key", "secret", "token", "كلمة المرور")


class RiskPrediction(NamedTuple):
    risk_level: RiskLevel
    confidence: float
    explanation: str


logger = logging.getLogger("sitr.risk_classifier")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sitr-risk")
_lock = threading.Lock()
_pipeline = None
_state = {"model": MODEL_ID, "state": "not loaded", "detail": ""}


def status() -> dict:
    """Model state for the UI: not loaded, ready, unavailable, or disabled."""
    return dict(_state)


def _load():
    global _pipeline
    with _lock:
        if _pipeline is None:
            from transformers import pipeline

            _pipeline = pipeline("zero-shot-classification", model=MODEL_ID, device="cpu")
            _state.update(state="ready", detail="")
    return _pipeline


def _predict(text: str) -> RiskPrediction:
    result = _load()(text[:_MAX_CHARS], list(LABELS), hypothesis_template=HYPOTHESIS)
    label, score = result["labels"][0], float(result["scores"][0])
    return RiskPrediction(LABELS[label], round(score, 3), f"The text reads as {label}.")


def fallback(text: str) -> RiskPrediction:
    """Keyword rules used when the model is off or fails."""
    lowered = text.lower()
    if any(term in lowered for term in _CREDENTIAL_TERMS):
        return RiskPrediction(
            "critical", _FALLBACK_CONFIDENCE, "Fallback rules: the text mentions credentials."
        )
    if any(term in lowered for term in _CONFIDENTIAL_TERMS):
        return RiskPrediction(
            "high", _FALLBACK_CONFIDENCE, "Fallback rules: the text mentions confidential terms."
        )
    return RiskPrediction(
        "low", _FALLBACK_CONFIDENCE, "Fallback rules: no confidential terms were found."
    )


def classify_risk(text: str) -> RiskPrediction:
    """Predict semantic risk. Never raises: on any model problem the fallback answers."""
    if os.environ.get("SITR_HF_MODELS", "1") == "0":
        _state.update(state="disabled", detail="SITR_HF_MODELS=0")
        return fallback(text)
    if not text.strip():
        return RiskPrediction("low", 1.0, "The text is empty.")
    try:
        return _executor.submit(_predict, text).result(timeout=TIMEOUT_SECONDS)
    except FutureTimeout:
        _state.update(state="unavailable", detail=f"timed out after {TIMEOUT_SECONDS:.0f} s")
    except Exception as exc:
        # Log the error type only; messages can quote the input.
        _state.update(state="unavailable", detail=type(exc).__name__)
    logger.warning("Risk model unavailable (%s); using fallback rules.", _state["detail"])
    return fallback(text)


def warm_up() -> None:
    """Load the model in the background so the first request is not slow."""
    if os.environ.get("SITR_HF_MODELS", "1") != "0":
        _executor.submit(_load)
