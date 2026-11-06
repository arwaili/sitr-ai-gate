"""Lane 2 mock NER. OpenMed/privacy-filter-multilingual-v2 replaces this."""

import re

from src.contracts import SensitiveEntity

# shortcut: matches fixed synthetic names only, replace with the real model at Checkpoint C
_MOCK_NAMES = re.compile(r"Mariam Al-Example|مريم المثال")


def detect_entities(text: str) -> list[SensitiveEntity]:
    """Return contextual entities, with offsets into the exact input string."""
    return [
        SensitiveEntity(
            entity_type="PERSON",
            value=match.group(),
            start=match.start(),
            end=match.end(),
            confidence=0.9,
            source="hf_ner",
            severity="medium",
        )
        for match in _MOCK_NAMES.finditer(text)
    ]
