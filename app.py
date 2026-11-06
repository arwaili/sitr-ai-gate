"""Sitr Gradio interface. All security decisions come from inspect_and_process."""

import logging
import threading
from collections import Counter
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

# A fixed list, so free text can never reach a model through the task field.
TASKS = [
    ("Summarize · لخّص", "summarize"),
    ("Answer the request · أجب عن الطلب", "answer the request"),
    ("Rewrite professionally · أعد الصياغة", "rewrite professionally"),
    ("Translate to English · ترجم إلى الإنجليزية", "translate to English"),
    ("Translate to Arabic · ترجم إلى العربية", "translate to Arabic"),
]

BADGES = {
    "allow": ("#166534", "ALLOWED · مسموح"),
    "redact": ("#92400e", "REDACTED · تم الإخفاء"),
    "private": ("#1e40af", "PRIVATE ROUTE · معالجة خاصة"),
    "block": ("#991b1b", "BLOCKED · محظور"),
}
ROUTES = {
    "allow": "Approved external: Qwen through Hugging Face Inference · خارجي معتمد",
    "redact": "Sanitized external: Qwen sees placeholders only · خارجي منقّح",
    "private": "Private: Qwen inside Sitr, nothing leaves · خاص داخل سِتر",
    "block": "None: no model was called · لم يُستدعَ أي نموذج",
}
ACTION_ORDER = ("allow", "redact", "private", "block", "error")
ACTION_LABELS = {
    "allow": "Allowed · مسموح",
    "redact": "Redacted · منقّح",
    "private": "Private · خاص",
    "block": "Blocked · محظور",
    "error": "Errors · أخطاء",
}
# Uploads are stored by Gradio on drop, so one that is never inspected is purged on this schedule.
CACHE_PURGE_SECONDS = (600, 600)
# Mixed Arabic and English: each paragraph takes the direction of its first strong letter.
CSS = """
.sitr-text textarea, .sitr-text .textfield, .sitr-text .prose {
  unicode-bidi: plaintext; text-align: start; white-space: pre-wrap;
}
.sitr-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px; }
.sitr-tile { border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 10px; }
.sitr-tile b { display: block; font-size: 1.6rem; }
"""

# Dashboard counts: decisions and entity types only, in memory, shared by every visitor.
_stats: Counter = Counter()
_entity_stats: Counter = Counter()
_stats_lock = threading.Lock()


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


def starts_rtl(text: str) -> bool:
    """True when the first letter is Arabic, the same rule the browser uses for one paragraph."""
    first = next((c for c in text if c.isalpha()), "")
    return "\u0600" <= first <= "\u06ff"


def entity_counts(entities: list[dict]) -> str:
    counts = Counter(entity["entity_type"] for entity in entities)
    return ", ".join(f"{kind} × {n}" for kind, n in counts.most_common()) or "None · لا شيء"


def render(result: dict) -> tuple[str, str, list, str, str, str]:
    """Convert a FinalResponse dict into the values of the result components."""
    analysis = result["analysis"]
    is_error = result["status"] == "error"
    color, label = ("#374151", "ERROR · خطأ") if is_error else BADGES[result["action_taken"]]
    badge = (
        f'<div style="background:{color};color:#fff;padding:12px 16px;border-radius:8px;'
        f'font-size:1.25rem;font-weight:700">{escape(label)}</div>'
    )
    score = f"{analysis['risk_level']} ({analysis['risk_score']}/100)"
    risk = "Not assessed" if is_error else score
    route = "None: not inspected · لم يُفحص" if is_error else ROUTES[result["action_taken"]]
    why = (
        f"- **Risk:** {risk}\n- **Why:** {result['user_message']}\n- **Route:** {route}\n"
        f"- **Found:** {entity_counts(analysis['entities'])}"
    )
    redaction = result["redaction"]
    original = highlight(redaction["original_text"], analysis["entities"]) if redaction else []
    safe_text = redaction["safe_text"] if redaction else ""
    model_response = result["model_response"] or "No model was called."
    metadata = analysis["model_metadata"]
    rows = "\n".join(
        f"| {e['entity_type']} | {e['severity']} | {e['source']} | {e['confidence']:.2f} "
        f"| {e['page'] or '-'} |"
        for e in analysis["entities"]
    )
    details = (
        f"**Reason codes:** {', '.join(analysis['reason_codes']) or 'None'}\n\n"
        f"**Detector:** `{metadata['detector']}`\n\n**Classifier:** `{metadata['classifier']}`\n\n"
        f"**Latency:** {result['latency_ms']} ms\n\n"
        + (f"| Type | Severity | Source | Confidence | Page |\n|---|---|---|---|---|\n{rows}"
           if rows else "No findings.")
    )
    return badge, why, original, safe_text, model_response, details


def record(result: dict) -> None:
    with _stats_lock:
        _stats["error" if result["status"] == "error" else result["action_taken"]] += 1
        _entity_stats.update(entity["entity_type"] for entity in result["analysis"]["entities"])


def dashboard() -> str:
    with _stats_lock:
        stats, entities = Counter(_stats), Counter(_entity_stats)
    tiles = "".join(
        f'<div class="sitr-tile">{escape(ACTION_LABELS[a])}<b>{stats[a]}</b></div>'
        for a in ACTION_ORDER
    )
    total = f'<div class="sitr-tile">Inspected · فُحص<b>{sum(stats.values())}</b></div>'
    rows = "".join(
        f"<tr><td>{escape(kind)}</td><td>{n}</td></tr>" for kind, n in entities.most_common()
    )
    table = (
        f"<table><tr><th>Entity type</th><th>Found</th></tr>{rows}</table>"
        if rows else "<p>No findings yet.</p>"
    )
    return f'<div class="sitr-tiles">{total}{tiles}</div><h3>Entity categories</h3>{table}'


def readiness() -> str:
    """One line on whether each model is ready, for the header."""
    parts = [
        ("PII detector", hf_detection.status()["state"]),
        ("Risk classifier", risk_classifier.status()["state"]),
    ]
    return " · ".join(f"{name}: **{state}**" for name, state in parts)


def analyze(text: str, file_path: str | None, task: str) -> tuple:
    # Uploads are Gradio temp copies; Sitr deletes them once inspected, even on failure, and
    # the None at the end clears the file box so it never points at a deleted file.
    result = inspect_and_process(
        text=text or None, file_path=file_path, user_intent=task or "summarize",
        delete_file=bool(file_path),
    )
    record(result)
    badge, why, original, safe_text, response, details = render(result)
    rtl = bool(result["redaction"]) and starts_rtl(result["redaction"]["original_text"])
    # The highlighted view is a row of separate segments, so its direction is set as a whole.
    original = gr.HighlightedText(value=original, rtl=rtl)
    return badge, why, original, safe_text, response, details, dashboard(), readiness(), None


def enable_audit_log() -> None:
    """Write Sitr's metadata-only audit events to the console. Safe to call twice."""
    logger = logging.getLogger("sitr")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())


def warm_up() -> None:
    """Load every model in the background, then run each detector once.

    A request that arrives before the PII detector is ready is blocked, so the demo should
    wait until the header says ready.
    """
    for module in (hf_detection, risk_classifier, router):
        module.warm_up()

    def first_run() -> None:
        hf_detection.detect_entities("Warm-up for a public notice.")
        risk_classifier.classify_risk("Warm-up for a public notice.")

    threading.Thread(target=first_run, daemon=True).start()


with gr.Blocks(title="Sitr AI Gate", delete_cache=CACHE_PURGE_SECONDS) as demo:
    gr.Markdown(
        "# Sitr AI Gate · سِتر\n"
        "Inspects employee prompts and files before they reach an AI model, then allows, "
        "redacts, routes privately, or blocks them.\n\n"
        '<p dir="rtl">يفحص سِتر طلبات الموظفين وملفاتهم قبل وصولها إلى نماذج الذكاء '
        "الاصطناعي.</p>\n\n"
        "**Security decision-support prototype. Use synthetic data only; do not upload real "
        "confidential information.**"
    )
    status_output = gr.Markdown(readiness())
    with gr.Tab("Inspect · فحص"):
        with gr.Row():
            with gr.Column():
                example = gr.Dropdown(
                    list(EXAMPLES), value=None, label="Synthetic example · مثال اصطناعي"
                )
                text_input = gr.Textbox(
                    lines=8, label="Prompt or code · النص أو الكود", elem_classes="sitr-text"
                )
                file_input = gr.File(
                    label="Or upload a PDF, code or text file · أو ارفع ملفًا", type="filepath"
                )
                task_input = gr.Dropdown(TASKS, value="summarize", label="Task · المهمة")
                submit = gr.Button("Inspect · فحص", variant="primary")
            with gr.Column():
                badge_output = gr.HTML(label="Action")
                why_output = gr.Markdown(elem_classes="sitr-text")
                response_output = gr.Textbox(
                    label="Model response · رد النموذج", lines=4, elem_classes="sitr-text"
                )
        with gr.Row():
            original_output = gr.HighlightedText(
                label="Original with findings · النص الأصلي مع ما وُجد",
                elem_classes="sitr-text",
            )
            safe_output = gr.Textbox(
                label="Sanitized · النص المنقّح", lines=8, elem_classes="sitr-text"
            )
        with gr.Accordion("Technical details · التفاصيل التقنية", open=False):
            details_output = gr.Markdown()
    with gr.Tab("Dashboard · لوحة المتابعة"):
        gr.Markdown(
            "Counts since the app started, for every visitor. Only decisions and entity types "
            "are counted, never content."
        )
        dashboard_output = gr.HTML(dashboard())
        gr.Button("Refresh · تحديث").click(dashboard, None, dashboard_output)
    with gr.Tab("About · حول"):
        gr.Markdown(
            "**How a request flows:** rules for secrets and IDs, then "
            "`OpenMed/privacy-filter-multilingual-v2` for names and personal data and "
            "`Horizon-Labs/multilingual-zeroshot-small` for meaning, then a fixed policy.\n\n"
            "- **Allow:** the text goes to `Qwen/Qwen2.5-1.5B-Instruct` through Hugging Face "
            "Inference Providers.\n"
            "- **Redact:** only the text with placeholders such as `[EMAIL_1]` goes out.\n"
            "- **Private:** Qwen runs inside this app, so the original never leaves it. This is "
            "a demonstration, not an isolated environment.\n"
            "- **Block:** no model sees the text, not even the local ones.\n\n"
            "Evaluation data: "
            "[arwaili/sitr-synthetic-dlp](https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp)."
            " Audit logs hold decisions and counts, never content. Uploads are deleted after "
            "inspection."
        )

    example.change(lambda name: EXAMPLES.get(name, ""), example, text_input)
    submit.click(
        analyze,
        [text_input, file_input, task_input],
        [badge_output, why_output, original_output, safe_output, response_output,
         details_output, dashboard_output, status_output, file_input],
    )
    gr.Timer(5).tick(readiness, None, status_output)
    demo.load(readiness, None, status_output)

if __name__ == "__main__":
    enable_audit_log()
    warm_up()
    demo.launch(css=CSS)
