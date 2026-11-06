"""Lane 2 contextual PII detection with OpenMed/privacy-filter-multilingual-v2.

The model loads on first use, runs on CPU, and stays cached. If it cannot load or run in time,
`detect_entities` returns no findings and `status()` says why: Lane 1's rules still run, so
security never depends on this model. Set SITR_HF_MODELS=0 to turn it off.
"""

import logging
import os
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from src.contracts import SensitiveEntity

MODEL_ID = "OpenMed/privacy-filter-multilingual-v2"
# Tuned on the dev split: a token is part of an entity when P(not an entity) < ENTITY_GATE, and a
# finished entity is kept when its mean entity probability is at least THRESHOLD.
ENTITY_GATE = 0.5
THRESHOLD = 0.7
TIMEOUT_SECONDS = float(os.environ.get("SITR_MODEL_TIMEOUT", "30"))
_CHUNK_CHARS = 2000

# OpenMed label -> (Sitr entity type, severity). Unlisted labels (city, date, job title,
# organization, amounts) are not sensitive enough on their own and are ignored.
LABEL_MAP = {
    "FIRSTNAME": ("PERSON", "medium"),
    "MIDDLENAME": ("PERSON", "medium"),
    "LASTNAME": ("PERSON", "medium"),
    "EMAIL": ("EMAIL", "medium"),
    "PHONE": ("PHONE", "medium"),
    "STREET": ("ADDRESS", "medium"),
    "BUILDINGNUMBER": ("ADDRESS", "medium"),
    "SECONDARYADDRESS": ("ADDRESS", "medium"),
    "ZIPCODE": ("ADDRESS", "medium"),
    "DATEOFBIRTH": ("DATE_OF_BIRTH", "medium"),
    "USERNAME": ("USERNAME", "medium"),
    "IBAN": ("IBAN", "high"),
    "BANKACCOUNT": ("ACCOUNT_NUMBER", "high"),
    "CREDITCARD": ("CREDIT_CARD", "high"),
    "CVV": ("CREDIT_CARD", "high"),
    "SSN": ("NATIONAL_ID", "high"),
    "PIN": ("PIN", "high"),
    "PASSWORD": ("PASSWORD", "critical"),
}

# Words the model has read as names that never are: Qatari places and confidentiality terms.
# A PERSON finding made only of these words is dropped.
NOT_NAMES = {
    "doha", "qatar", "lusail", "wakrah", "al", "khor", "corniche", "pearl", "katara",
    "الدوحة", "دوحة", "قطر", "لوسيل", "الوكرة", "الخور", "الكورنيش", "كتارا",
    "سري", "سرية", "السنوي", "الموظف", "الموظفة",
}

logger = logging.getLogger("sitr.hf_detection")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sitr-ner")
_lock = threading.Lock()
_model = None
_state = {"model": MODEL_ID, "state": "not loaded", "detail": ""}


def status() -> dict:
    """Model state for the UI: not loaded, ready, unavailable, or disabled."""
    return dict(_state)


def _load():
    global _model
    with _lock:
        if _model is None:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
            model = AutoModelForTokenClassification.from_pretrained(MODEL_ID, dtype=torch.bfloat16)
            model.eval()
            _model = (tokenizer, model, torch)
            _state.update(state="ready", detail="")
    return _model


def _chunks(text: str):
    """Yield (offset, piece) windows that end on a line break where possible."""
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_CHARS, len(text))
        if end < len(text):
            cut = text.rfind("\n", start, end)
            end = cut + 1 if cut > start else end
        yield start, text[start:end]
        start = end


def _is_word_char(char: str) -> bool:
    # Letters, digits, and combining marks such as Arabic shadda.
    return char.isalnum() or unicodedata.category(char).startswith("M")


def decode(text: str, offsets, labels, scores) -> list[SensitiveEntity]:
    """Turn per-token BIOES labels and entity probabilities into entities with exact offsets."""
    spans: list[list] = []  # [kind, start, end, [scores]]
    open_span = None
    for (start, end), label, score in zip(offsets, labels, scores, strict=True):
        if end <= start or label == "O":
            open_span = None
            continue
        prefix, kind = label.split("-", 1)
        if open_span is None or prefix in ("B", "S") or open_span[0] != kind:
            open_span = [kind, start, end, [score]]
            spans.append(open_span)
        else:
            open_span[2] = end
            open_span[3].append(score)
        if prefix in ("E", "S"):
            open_span = None
    entities: list[SensitiveEntity] = []
    for kind, start, end, span_scores in spans:
        if kind not in LABEL_MAP:
            continue
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        # Tokens can split a word; a span that cuts a word grows to the whole word.
        while 0 < start < end and _is_word_char(text[start - 1]):
            start -= 1
        while start < end < len(text) and _is_word_char(text[end]):
            end += 1
        confidence = sum(span_scores) / len(span_scores)
        if end <= start:
            continue
        entity_type, severity = LABEL_MAP[kind]
        previous = entities[-1] if entities else None
        # First and last name come back as separate spans; join same-type spans split by spaces.
        same_kind = previous is not None and previous.entity_type == entity_type
        if same_kind and not text[previous.end : start].strip():
            end = max(end, previous.end)
            entities[-1] = previous.model_copy(update={
                "end": end,
                "value": text[previous.start : end],
                "confidence": round(min(previous.confidence, confidence), 3),
            })
            continue
        entities.append(SensitiveEntity(
            entity_type=entity_type,
            value=text[start:end],
            start=start,
            end=end,
            confidence=round(confidence, 3),
            source="hf_ner",
            severity=severity,
        ))
    return [e for e in entities if e.confidence >= THRESHOLD and _plausible(e)]


def _plausible(entity: SensitiveEntity) -> bool:
    """Cheap shape checks that drop model fragments such as a port number tagged as an email."""
    if entity.entity_type == "PERSON":
        return not all(word.casefold() in NOT_NAMES for word in entity.value.split())
    if entity.entity_type == "EMAIL":
        return "@" in entity.value
    if entity.entity_type in ("PHONE", "ACCOUNT_NUMBER", "CREDIT_CARD"):
        return sum(c.isdigit() for c in entity.value) >= 7
    return True


def _predict(text: str) -> list[SensitiveEntity]:
    tokenizer, model, torch = _load()
    id2label = model.config.id2label
    outside = model.config.label2id["O"]
    entities: list[SensitiveEntity] = []
    for offset, piece in _chunks(text):
        encoded = tokenizer(piece, return_offsets_mapping=True, return_tensors="pt")
        offsets = encoded.pop("offset_mapping")[0].tolist()
        with torch.inference_mode():
            probabilities = model(**encoded).logits[0].float().softmax(-1)
            p_outside = probabilities[:, outside].tolist()
            probabilities[:, outside] = 0
            best = probabilities.argmax(-1).tolist()
        labels = [
            id2label[i] if p < ENTITY_GATE else "O"
            for i, p in zip(best, p_outside, strict=True)
        ]
        found = decode(piece, offsets, labels, [1 - p for p in p_outside])
        entities += [
            e.model_copy(update={"start": e.start + offset, "end": e.end + offset}) for e in found
        ]
    return entities


class DetectorUnavailable(Exception):
    """The detector could not run. Carries no input content."""


def require_entities(text: str) -> list[SensitiveEntity]:
    """Return contextual entities, or raise DetectorUnavailable if the model could not run.

    Rules cannot see names, so callers that send text onward must use this one: an empty list
    here means the model looked and found nothing, not that it failed.
    """
    if os.environ.get("SITR_HF_MODELS", "1") == "0":
        _state.update(state="disabled", detail="SITR_HF_MODELS=0")
        return []
    if not text.strip():
        return []
    try:
        entities = _executor.submit(_predict, text).result(timeout=TIMEOUT_SECONDS)
    except FutureTimeout:
        # The call keeps running in the background and the next call reuses the loaded model.
        _state.update(state="unavailable", detail=f"timed out after {TIMEOUT_SECONDS:.0f} s")
    except Exception as exc:
        # Log the error type only; messages can quote the input.
        _state.update(state="unavailable", detail=type(exc).__name__)
    else:
        _state.update(state="ready", detail="")
        return entities
    logger.warning("PII model unavailable (%s).", _state["detail"])
    raise DetectorUnavailable


def detect_entities(text: str) -> list[SensitiveEntity]:
    """Return contextual entities with offsets into the exact input; `[]` if the model failed."""
    try:
        return require_entities(text)
    except DetectorUnavailable:
        return []


def warm_up() -> None:
    """Load the model in the background so the first request is not slow."""
    if os.environ.get("SITR_HF_MODELS", "1") != "0":
        _executor.submit(_load)
