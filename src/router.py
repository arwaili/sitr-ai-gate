"""Send permitted prompts to the right model route. Blocked content never gets here.

- approved_external (allow) and sanitized_external (redact, placeholders only) call
  Qwen/Qwen2.5-1.5B-Instruct through Hugging Face Inference Providers.
- private_simulation (private) runs the same Qwen model inside the Sitr process, so the
  original text never leaves it. It is a demonstration, not an isolated environment.
SITR_LLM=mock returns canned text (tests use it); a model failure returns a notice, never
raises, and never changes Sitr's decision.
"""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from src.contracts import Action, RedactionResult

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
# The provider must be named: it is not among the account's default providers.
PROVIDER = os.environ.get("SITR_LLM_PROVIDER", "featherless-ai")
EXTERNAL_TIMEOUT = float(os.environ.get("SITR_LLM_TIMEOUT", "30"))
PRIVATE_TIMEOUT = float(os.environ.get("SITR_PRIVATE_TIMEOUT", "60"))
PRIVATE_MAX_TOKENS = 96
_MAX_PROMPT_CHARS = 6000

ROUTES = {
    "allow": "approved_external",
    "redact": "sanitized_external",
    "private": "private_simulation",
}
PRIVATE_LABEL = "[Private route: answered by Qwen running inside Sitr, not by an external service]"
_SYSTEM = (
    "You are a helpful workplace assistant. Text in square brackets such as [EMAIL_1] stands "
    "for a value that was removed for privacy: keep it unchanged and never guess it. Reply "
    "briefly, only in English or Arabic, matching the text. If the text is itself a request, "
    "answer it."
)

logger = logging.getLogger("sitr.router")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sitr-private-llm")
_lock = threading.Lock()
_local = None


def _messages(prompt: str, user_intent: str) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Task: {user_intent}\n\n{prompt[:_MAX_PROMPT_CHARS]}"},
    ]


def _external(prompt: str, user_intent: str) -> str:
    from huggingface_hub import InferenceClient

    client = InferenceClient(model=MODEL_ID, provider=PROVIDER, timeout=EXTERNAL_TIMEOUT)
    reply = client.chat_completion(messages=_messages(prompt, user_intent), max_tokens=300)
    return reply.choices[0].message.content.strip()


def _generate_locally(prompt: str, user_intent: str) -> str:
    global _local
    with _lock:
        if _local is None:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
            model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.bfloat16)
            _local = (tokenizer, model.eval(), torch)
    tokenizer, model, torch = _local
    encoded = tokenizer.apply_chat_template(
        _messages(prompt, user_intent), add_generation_prompt=True,
        return_tensors="pt", return_dict=True,
    )
    with torch.inference_mode():
        output = model.generate(**encoded, max_new_tokens=PRIVATE_MAX_TOKENS, do_sample=False)
    new_tokens = output[0, encoded["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def _private(prompt: str, user_intent: str) -> str:
    future = _executor.submit(_generate_locally, prompt, user_intent)
    return f"{PRIVATE_LABEL}\n{future.result(timeout=PRIVATE_TIMEOUT)}"


def call_model(route: str, prompt: str, user_intent: str) -> str:
    """The replaceable model adapter. Never raises."""
    if os.environ.get("SITR_LLM", "live") == "mock":
        if route == "private_simulation":
            return f"[Mock private route] The '{user_intent}' response would appear here."
        return f"[Mock approved model] The '{user_intent}' response would appear here."
    try:
        if route == "private_simulation":
            return _private(prompt, user_intent)
        return _external(prompt, user_intent)
    except FutureTimeout:
        reason = "it took too long"
    except Exception as exc:
        # Log the error type only; messages can quote the prompt.
        reason = type(exc).__name__
        logger.warning("Model route %s failed (%s).", route, reason)
    return f"The model could not answer ({reason}). Sitr's decision above still applies."


def warm_up() -> None:
    """Load the private-route model in the background so the first private request is quicker."""
    if os.environ.get("SITR_LLM", "live") != "mock":
        _executor.submit(_generate_locally, "Hello", "reply")


def route(action: Action, redaction: RedactionResult, user_intent: str) -> str | None:
    """Return the model response, or None when the action is block."""
    if action == "block":
        return None
    # Only the sanitized text may leave on the redact route; private keeps the original inside.
    prompt = redaction.safe_text if action == "redact" else redaction.original_text
    return call_model(ROUTES[action], prompt, user_intent)
