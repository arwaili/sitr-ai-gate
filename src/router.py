"""Send permitted prompts to the right model route. Blocked content never gets here."""

from src.contracts import Action, RedactionResult

ROUTES = {
    "allow": "approved_external",
    "redact": "sanitized_external",
    "private": "private_simulation",
}


def call_model(route: str, prompt: str, user_intent: str) -> str:
    """Mock model adapter. Qwen/Qwen2.5-1.5B-Instruct replaces this, behind the same signature."""
    if route == "private_simulation":
        return f"[Mock private route, simulated] The '{user_intent}' response would appear here."
    return f"[Mock approved model] The '{user_intent}' response would appear here."


def route(action: Action, redaction: RedactionResult, user_intent: str) -> str | None:
    """Return the model response, or None when the action is block."""
    if action == "block":
        return None
    # Only the sanitized text may leave on the redact route; private keeps the original inside.
    prompt = redaction.safe_text if action == "redact" else redaction.original_text
    return call_model(ROUTES[action], prompt, user_intent)
