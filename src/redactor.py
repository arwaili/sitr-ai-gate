"""Replace detected values with stable placeholders such as [EMAIL_1]."""

from src.contracts import RedactionResult, Replacement, SensitiveEntity


def redact(text: str, entities: list[SensitiveEntity]) -> RedactionResult:
    """Redact every entity. Overlapping spans merge, so no part of a value survives."""
    spans: list[list] = []
    for entity in sorted(entities, key=lambda item: (item.start, -item.end)):
        if spans and entity.start < spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], entity.end)
        else:
            spans.append([entity.start, entity.end, entity.entity_type])

    placeholders: dict[str, str] = {}
    replacements: list[Replacement] = []
    parts: list[str] = []
    cursor = 0
    for start, end, entity_type in spans:
        value = text[start:end]
        if value not in placeholders:
            prefix = f"[{entity_type}_"
            count = sum(placeholder.startswith(prefix) for placeholder in placeholders.values())
            placeholders[value] = f"{prefix}{count + 1}]"
            replacements.append(
                Replacement(
                    placeholder=placeholders[value], entity_type=entity_type, original_value=value
                )
            )
        parts += [text[cursor:start], placeholders[value]]
        cursor = end
    parts.append(text[cursor:])
    return RedactionResult(original_text=text, safe_text="".join(parts), replacements=replacements)
