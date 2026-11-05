"""Privacy-safe audit events: decision metadata only, never content or detected values."""

import json
import logging
import os
from collections import Counter
from datetime import UTC, datetime

from src.contracts import FinalResponse

logger = logging.getLogger("sitr.audit")


def build_event(response: FinalResponse, input_type: str) -> dict:
    analysis = response.analysis
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": analysis.document_id,
        "input_type": input_type,
        "entity_counts": dict(Counter(entity.entity_type for entity in analysis.entities)),
        "risk_level": analysis.risk_level,
        "action": response.action_taken,
        "reason_codes": analysis.reason_codes,
        "latency_ms": response.latency_ms,
        "model_versions": analysis.model_metadata.model_dump(),
        "success": response.status != "error",
    }


def record(response: FinalResponse, input_type: str) -> None:
    if os.getenv("SITR_AUDIT_ENABLED", "true").lower() == "true":
        logger.info(json.dumps(build_event(response, input_type)))
