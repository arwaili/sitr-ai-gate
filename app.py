"""Sitr Gradio interface. All security decisions come from inspect_and_process."""

import logging
from html import escape

import gradio as gr

from src import hf_detection, risk_classifier, router
from src.orchestrator import inspect_and_process

# Every value below is synthetic.
EXAMPLES = {
    "Safe public prompt": "Write a public marketing slogan for a Doha cafe.",
    "Synthetic CV": "Curriculum vitae: Mariam Al-Example\n"
    "Email: test.applicant@example.com\nPhone: +974 0000 0100",
    "Synthetic Arabic-English contract": "عقد عمل / Employment contract\n"
    "الموظف: مريم المثال\nالراتب: 15000 ريال\nالرقم الشخصي: 28400000000",
    "Code with a synthetic API key": 'API_KEY = "sk-synthetic-000000000000"\n'
    'requests.get(URL, headers={"Authorization": API_KEY})',
}

# Uploads are stored by Gradio on drop, so one that is never inspected is purged on this schedule.
CACHE_PURGE_SECONDS = (600, 600)

BADGES = {
    "allow": ("#166534", "ALLOWED · مسموح"),
    "redact": ("#92400e", "REDACTED · تم الإخفاء"),
    "private": ("#1e40af", "PRIVATE ROUTE · معالجة خاصة"),
    "block": ("#991b1b", "BLOCKED · محظور"),
}


def highlight(text: str, entities: list[dict]) -> list[tuple[str, str | None]]:
    """Split text into labeled segments, skipping any entity overlapping an earlier one."""
    segments: list[tuple[str, str | None]] = []
    cursor = 0
    for entity in sorted(entities, key=lambda item: item["start"]):
        if entity["start"] < cursor:
            continue
        segments += [
            (text[cursor : entity["start"]], None),
            (text[entity["start"] : entity["end"]], entity["entity_type"]),
        ]
        cursor = entity["end"]
    segments.append((text[cursor:], None))
    return segments


def render(result: dict) -> tuple[str, str, list, str, str, str]:
    """Convert a FinalResponse dict into the values of the result components."""
    analysis = result["analysis"]
    is_error = result["status"] == "error"
    color, label = ("#374151", "ERROR · خطأ") if is_error else BADGES[result["action_taken"]]
    badge = (
        f'<div style="background:{color};color:#fff;padding:12px 16px;border-radius:8px;'
        f'font-size:1.25rem;font-weight:700">{escape(label)}</div>'
    )
    reasons = ", ".join(analysis["reason_codes"]) or "None"
    score = f"{analysis['risk_level']} ({analysis['risk_score']}/100)"
    risk = "Not assessed" if is_error else score
    why = f"**Risk:** {risk}\n\n**Why:** {result['user_message']}\n\n**Reason codes:** {reasons}"
    redaction = result["redaction"]
    original = highlight(redaction["original_text"], analysis["entities"]) if redaction else []
    safe_text = redaction["safe_text"] if redaction else ""
    model_response = result["model_response"] or "No model was called."
    metadata = analysis["model_metadata"]
    models = (
        f"Detector: `{metadata['detector']}` · Classifier: `{metadata['classifier']}` · "
        f"{result['latency_ms']} ms"
    )
    return badge, why, original, safe_text, model_response, models


def analyze(text: str, file_path: str | None) -> tuple[str, str, list, str, str, str, None]:
    # Uploads are Gradio temp copies; Sitr deletes them once inspected, even on failure, and
    # the last value clears the file box so it never points at a deleted file.
    result = inspect_and_process(
        text=text or None, file_path=file_path, delete_file=bool(file_path)
    )
    return (*render(result), None)


def enable_audit_log() -> None:
    """Write Sitr's metadata-only audit events to the console. Safe to call twice."""
    logger = logging.getLogger("sitr")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())


with gr.Blocks(title="Sitr AI Gate", delete_cache=CACHE_PURGE_SECONDS) as demo:
    gr.Markdown(
        "# Sitr AI Gate · سِتر\n"
        "Inspects employee prompts and files before they reach an AI model, then allows, "
        "redacts, routes privately, or blocks them.\n\n"
        "**Security decision-support prototype. Do not upload real confidential information.**\n\n"
        "*The private route runs Qwen inside this app; it is a demonstration, not an isolated "
        "environment.*"
    )
    with gr.Row():
        with gr.Column():
            example = gr.Dropdown(
                list(EXAMPLES), value=None, label="Synthetic example · مثال اصطناعي"
            )
            text_input = gr.Textbox(lines=8, label="Prompt or code · النص أو الكود")
            file_input = gr.File(label="Or upload a file · أو ارفع ملفًا", type="filepath")
            submit = gr.Button("Inspect · فحص", variant="primary")
        with gr.Column():
            badge_output = gr.HTML(label="Action")
            why_output = gr.Markdown()
            response_output = gr.Textbox(label="Model response · رد النموذج", lines=3)
            models_output = gr.Markdown()
    with gr.Row():
        original_output = gr.HighlightedText(label="Original with findings · النص الأصلي")
        safe_output = gr.Textbox(label="Sanitized · النص المنقّح", lines=8)

    example.change(lambda name: EXAMPLES.get(name, ""), example, text_input)
    submit.click(
        analyze,
        [text_input, file_input],
        [
            badge_output, why_output, original_output, safe_output, response_output, models_output,
            file_input,
        ],
    )

if __name__ == "__main__":
    enable_audit_log()
    for module in (hf_detection, risk_classifier, router):
        module.warm_up()
    demo.launch()
