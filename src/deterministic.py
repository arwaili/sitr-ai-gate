"""Lane 1 mock deterministic findings. Real regex and secret scanners replace this."""

import re

from src.contracts import SensitiveEntity

# shortcut: only two patterns, extend to the full detector list in instructions.md
_PATTERNS = [
    ("API_KEY", r"\bsk-[A-Za-z0-9_-]{8,}", "critical", "secret_scanner"),
    ("EMAIL", r"[\w.+-]+@[\w-]+\.[\w.-]+", "medium", "regex"),
]


def detect_deterministic(text: str) -> list[SensitiveEntity]:
    """Return one entity per occurrence, with offsets into the exact input string."""
    return [
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
