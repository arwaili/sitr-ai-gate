"""Sitr Gradio interface: a chat where every message is inspected before any model sees it.

All security decisions come from inspect_and_process; this file only shows them.
"""

import logging
import threading
from collections import Counter
from html import escape
from pathlib import Path

import gradio as gr

from src import hf_detection, risk_classifier, router
from src.orchestrator import inspect_and_process
from ui_text import (
    DECISION_REASONS_AR,
    ERROR_FALLBACK_AR,
    ERRORS_AR,
    NOTHING_SENT_AR,
    REASONS_AR,
    TEXT,
)

# Every value below is synthetic. Order matches TEXT[lang]["examples"].
EXAMPLES = {
    "Safe public prompt": "Write a public marketing slogan for a Doha cafe.",
    "Synthetic CV": "Curriculum vitae: Mariam Al-Example\n"
    "Email: test.applicant@example.com\nPhone: +974 0000 0100",
    "Synthetic Arabic-English contract": "عقد عمل / Employment contract\n"
    "الموظف: مريم المثال\nالراتب: 15000 ريال\nالرقم الشخصي: 28400000000",
    "Code with a synthetic API key": 'API_KEY = "sk-synthetic-000000000000"\n'
    'requests.get(URL, headers={"Authorization": API_KEY})',
}
EXAMPLE_TASKS = ["answer the request", "summarize", "summarize", "answer the request"]

# A fixed list, so free text can never reach a model through the task field.
TASK_VALUES = [
    "summarize", "answer the request", "rewrite professionally", "translate to English",
    "translate to Arabic",
]
TASKS = list(zip(TEXT["en"]["tasks"], TASK_VALUES, strict=True))

SEAL_WORDS_AR = {"allow": "مسموح", "redact": "منقّح", "private": "خاص", "block": "محظور",
                 "error": "لم يُفحص"}
ACTION_ORDER = ("allow", "redact", "private", "block", "error")
# Uploads are stored by Gradio on drop, so one that is never sent is purged on this schedule.
CACHE_PURGE_SECONDS = (600, 600)

THEME = gr.themes.Base(
    font=[gr.themes.GoogleFont("Readex Pro"), "system-ui", "sans-serif"],
    radius_size=gr.themes.sizes.radius_md,
).set(
    body_background_fill="#F2F4F3",
    body_background_fill_dark="#121917",
    body_text_color="#17201E",
    body_text_color_dark="#E6ECEA",
    block_background_fill="#FFFFFF",
    block_background_fill_dark="#1A2321",
    block_border_color="#D9E0DD",
    block_border_color_dark="#2A3532",
    border_color_primary="#D9E0DD",
    border_color_primary_dark="#2A3532",
    input_background_fill="#FFFFFF",
    input_background_fill_dark="#1A2321",
    block_label_text_color="#52615C",
    block_label_text_color_dark="#9DB0AA",
    color_accent="#8A1538",
    color_accent_soft="#F3E3E8",
    color_accent_soft_dark="#3A1824",
    button_primary_background_fill="#8A1538",
    button_primary_background_fill_hover="#6F102D",
    button_primary_background_fill_dark="#A8274E",
    button_primary_background_fill_hover_dark="#8A1538",
    button_primary_text_color="#FFFFFF",
    button_secondary_background_fill="#FFFFFF",
    button_secondary_background_fill_dark="#1A2321",
    button_secondary_border_color="#C9D2CE",
    button_secondary_border_color_dark="#34423E",
)
HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Reem+Kufi:wght@500;700&display=swap"'
    ' rel="stylesheet">'
)
# An eight-point star, the tile of a mashrabiya screen; used once, behind the header.
_LATTICE = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='44' height='44'%3E"
    "%3Cg fill='none' stroke='%238A1538' stroke-opacity='.07'%3E"
    "%3Crect x='12' y='12' width='20' height='20'/%3E"
    "%3Crect x='12' y='12' width='20' height='20' transform='rotate(45 22 22)'/%3E"
    "%3C/g%3E%3C/svg%3E"
)
CSS = f"""
:root {{
  --sitr-allow: #2F7A5B; --sitr-redact: #A8661B; --sitr-private: #24527A;
  --sitr-block: #8A1538; --sitr-error: #5B6763; --sitr-muted: #52615C;
  --sitr-medium: #F3DDB4; --sitr-high: #D3E1EE; --sitr-critical: #F1D0D9;
}}
.dark {{
  --sitr-allow: #5FB48D; --sitr-redact: #E0A24E; --sitr-private: #7FA8D2;
  --sitr-block: #E0708F; --sitr-error: #9DB0AA; --sitr-muted: #9DB0AA;
  --sitr-medium: #5A4220; --sitr-high: #233A52; --sitr-critical: #5A2333;
}}
/* One fixed column for every tab, so the header never changes size. */
.gradio-container {{ width: 100% !important; max-width: 860px !important; margin: 0 auto; }}
footer {{ display: none !important; }}
#sitr-top {{ position: relative; gap: 0; border-radius: 10px;
  background: url("{_LATTICE}") repeat; border-bottom: 3px solid var(--sitr-block); }}
#sitr-lang {{ position: absolute !important; top: 16px; inset-inline-end: 16px; z-index: 1;
  width: auto !important; min-width: 92px; height: auto !important; margin: 0; }}
#sitr-header {{ padding: 20px 22px 16px; }}
.sitr-wordmark {{ display: flex; align-items: baseline; gap: 12px; }}
.sitr-wordmark .ar {{ font-family: "Reem Kufi", "Readex Pro", sans-serif; font-weight: 700;
  font-size: 2.8rem; line-height: 1; color: var(--sitr-block); }}
.sitr-wordmark .en {{ font-size: 1.05rem; font-weight: 600; }}
.sitr-purpose {{ margin: 8px 0 10px; max-width: 58ch; color: var(--sitr-muted); }}
.sitr-ready {{ display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: .85rem; }}
.sitr-ready span::before {{ content: ""; display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-inline-end: 7px; background: var(--sitr-redact); }}
.sitr-ready span.ready::before {{ background: var(--sitr-allow); }}
.sitr-ready span.down::before {{ background: var(--sitr-block); }}
button[role="tab"].selected, button[role="tab"][aria-selected="true"] {{
  color: var(--sitr-block) !important; border-color: var(--sitr-block) !important; }}

#sitr-chat {{ border: 0 !important; background: transparent !important; }}
#sitr-chat .message {{ max-width: 100% !important; }}
#sitr-composer {{ border-radius: 22px !important; }}
#sitr-composer .upload-button, #sitr-composer .submit-button {{
  width: 34px !important; height: 34px !important; border-radius: 50% !important;
  display: inline-flex; align-items: center; justify-content: center; }}
#sitr-composer .upload-button {{ border: 1px solid var(--border-color-primary) !important; }}
#sitr-composer .upload-button svg {{ display: none; }}
#sitr-composer .upload-button::before {{ content: "+"; font-size: 1.5rem; font-weight: 300;
  line-height: 1; }}
#sitr-composer .submit-button {{ background: var(--sitr-block) !important; color: #fff !important;
  padding: 8px !important; }}
#sitr-tools {{ background: transparent !important; border: 0 !important; gap: 8px;
  justify-content: flex-start !important; align-items: center; }}
#sitr-task {{ margin: 0 !important; }}
#sitr-tools > * {{ flex: 0 1 auto !important; min-width: 0 !important; }}
#sitr-task {{ width: 260px; }}
.sitr-empty {{ text-align: center; padding: 28px 12px 8px; }}
.sitr-empty .ar {{ font-family: "Reem Kufi", "Readex Pro", sans-serif; font-size: 3.2rem;
  color: var(--sitr-block); line-height: 1; }}
.sitr-empty h3 {{ margin: 14px 0 6px; font-size: 1.25rem; }}
.sitr-empty p {{ margin: 0 auto; max-width: 46ch; color: var(--sitr-muted); }}

.sitr-user {{ white-space: pre-wrap; }}
.sitr-user [dir="auto"] {{ display: block; }}
.sitr-user .meta {{ display: block; margin-top: 8px; font-size: .82rem; opacity: .75; }}
.sitr-pending {{ color: var(--sitr-muted); }}
.sitr-reply {{ display: flex; flex-direction: column; gap: 14px; width: 100%; min-width: 0; }}
#sitr-chat .message-row.bot-row .message, #sitr-chat .bot {{ width: 100% !important; }}
.sitr-quote, .sitr-answer {{ overflow-wrap: anywhere; }}
/* Each line of quoted text, answers and user messages takes the direction of its first letter,
   so English code stays left to right inside the Arabic layout and the reverse. */
.sitr-quote, .sitr-answer, .sitr-user [dir="auto"] {{ unicode-bidi: plaintext;
  text-align: start; }}
div:has(> #sitr-composer), div:has(> #sitr-tools) {{ background: transparent !important;
  border: 0 !important; box-shadow: none !important; }}
.sitr-reply h4 {{ margin: 0 0 6px; font-size: .82rem; font-weight: 600;
  color: var(--sitr-muted); }}
.sitr-seal {{ border: 2px solid var(--seal); border-inline-start-width: 8px; border-radius: 8px;
  padding: 14px 18px; }}
.sitr-seal .word {{ font-family: "Reem Kufi", "Readex Pro", sans-serif; font-weight: 700;
  font-size: 2.2rem; line-height: 1.15; color: var(--seal); }}
.sitr-seal .word.latin {{ font-family: inherit; font-size: 1.7rem; }}
.sitr-seal .what {{ margin-top: 4px; }}
.sitr-seal.allow {{ --seal: var(--sitr-allow); }}
.sitr-seal.redact {{ --seal: var(--sitr-redact); }}
.sitr-seal.private {{ --seal: var(--sitr-private); }}
.sitr-seal.block {{ --seal: var(--sitr-block); }}
.sitr-seal.error {{ --seal: var(--sitr-error); }}
@media (prefers-reduced-motion: no-preference) {{
  .sitr-seal {{ animation: sitr-stamp .28s ease-out; }}
  @keyframes sitr-stamp {{ from {{ transform: scale(1.03); opacity: 0; }} }}
}}
.sitr-facts {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px;
  margin: 0 0 8px; }}
.sitr-facts dt {{ color: var(--sitr-muted); }}
.sitr-facts dd {{ margin: 0; }}
.sitr-quote {{ white-space: pre-wrap; padding: 10px 12px; border-radius: 8px;
  background: var(--body-background-fill); border: 1px solid var(--border-color-primary);
  line-height: 1.9; }}
.sitr-quote mark {{ border-radius: 4px; padding: 1px 4px; color: inherit; }}
.sitr-quote mark small {{ font-size: .66rem; font-weight: 600; margin-inline-start: 4px;
  opacity: .8; }}
.sitr-quote mark.medium {{ background: var(--sitr-medium); }}
.sitr-quote mark.high {{ background: var(--sitr-high); }}
.sitr-quote mark.critical {{ background: var(--sitr-critical); }}
.sitr-note {{ margin-top: 6px; font-size: .85rem; color: var(--sitr-muted); }}
.sitr-answer {{ white-space: pre-wrap; }}
.sitr-reply details summary {{ cursor: pointer; color: var(--sitr-muted); font-size: .85rem; }}
.sitr-table {{ border-collapse: collapse; margin-top: 8px; font-size: .85rem; }}
.sitr-table td, .sitr-table th {{ padding: 4px 12px 4px 0; text-align: start;
  border-bottom: 1px solid var(--border-color-primary); }}

.sitr-bar {{ display: flex; height: 28px; border-radius: 6px; overflow: hidden;
  background: var(--border-color-primary); }}
.sitr-bar span {{ display: block; }}
.sitr-legend {{ display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 12px 0 20px; }}
.sitr-legend b {{ font-size: 1.4rem; margin-inline-start: 6px; }}
.sitr-legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-inline-end: 6px; }}
/* Gradio stamps dir="ltr" on every block; in Arabic mode the page direction wins. */
html[dir="rtl"] .gradio-container [dir="ltr"] {{ direction: rtl; }}
@media (max-width: 640px) {{
  #sitr-header {{ padding: 58px 14px 14px; }}
  .sitr-wordmark .ar {{ font-size: 2.4rem; }}
}}
"""

# Arabic reads right to left, so the whole page flips with the language. State never reaches
# the browser, so this reads the switch button, which offers "English" only while in Arabic.
SET_DIRECTION_JS = """(label) => { const ar = label === "English";
  document.documentElement.lang = ar ? "ar" : "en";
  document.documentElement.dir = ar ? "rtl" : "ltr"; }"""

# Dashboard counts: decisions and entity types only, in memory, shared by every visitor.
_stats: Counter = Counter()
_entity_stats: Counter = Counter()
_stats_lock = threading.Lock()


def _dir(lang: str) -> str:
    return "rtl" if lang == "ar" else "ltr"


def _decision(result: dict) -> str:
    return "error" if result["status"] == "error" else result["action_taken"]


def findings_html(text: str, entities: list[dict]) -> str:
    """The text with each finding marked by its type, skipping any overlapping an earlier one."""
    parts, cursor = [], 0
    for entity in sorted(entities, key=lambda item: item["start"]):
        if entity["start"] < cursor:
            continue
        parts.append(escape(text[cursor : entity["start"]]))
        value = escape(text[entity["start"] : entity["end"]])
        parts.append(
            f'<mark class="{entity["severity"]}">{value}<small>{entity["entity_type"]}</small>'
            "</mark>"
        )
        cursor = entity["end"]
    parts.append(escape(text[cursor:]))
    return "".join(parts)


def entity_counts(entities: list[dict], lang: str = "en") -> str:
    counts = Counter(entity["entity_type"] for entity in entities)
    joiner = "، " if lang == "ar" else ", "
    return joiner.join(f"{kind} × {n}" for kind, n in counts.most_common()) or TEXT[lang][
        "nothing"
    ]


def reason(result: dict, lang: str = "en") -> str:
    """Why Sitr decided this, in the chosen language. The policy writes it in English."""
    if lang == "en":
        return result["user_message"]
    analysis, key = result["analysis"], _decision(result)
    if key == "error":
        return f"{ERRORS_AR.get(analysis['explanation'], ERROR_FALLBACK_AR)} {NOTHING_SENT_AR}"
    if key == "block":
        return REASONS_AR.get(analysis["reason_codes"][0], DECISION_REASONS_AR["block"])
    return DECISION_REASONS_AR[key]


def seal(result: dict, lang: str = "en") -> str:
    key = _decision(result)
    word = SEAL_WORDS_AR[key] if lang == "ar" else TEXT["en"]["decisions"][key]
    css = "word" if lang == "ar" else "word latin"
    return (
        f'<div class="sitr-seal {key}" role="status"><div class="{css}">{escape(word)}</div>'
        f'<div class="what">{escape(reason(result, lang))}</div></div>'
    )


def reply(result: dict, lang: str = "en") -> str:
    """Sitr's answer card, in the order things happen: decision, findings, what left, answer."""
    t, analysis, key = TEXT[lang], result["analysis"], _decision(result)
    risk = t["not_assessed"] if key == "error" else (
        f"{t['risk_levels'][analysis['risk_level']]}{'، ' if lang == 'ar' else ', '}"
        + t["of_100"].format(score=analysis["risk_score"])
    )
    facts = (
        f'<dl class="sitr-facts"><dt>{t["risk"]}</dt><dd>{escape(risk)}</dd>'
        f"<dt>{t['found']}</dt><dd>{escape(entity_counts(analysis['entities'], lang))}</dd>"
        f"<dt>{t['sent_to']}</dt><dd>{escape(t['routes'][key])}</dd></dl>"
    )
    redaction = result["redaction"]
    found = ""
    if redaction and analysis["entities"]:
        found = (
            f'<div class="sitr-quote" dir="auto">'
            f"{findings_html(redaction['original_text'], analysis['entities'])}</div>"
        )
    # On block or error nothing left Sitr, so no text is shown as sent.
    if key in ("block", "error") or not redaction:
        sent = f'<div class="sitr-note">{t["nothing_sent"]}</div>'
    else:
        shown = redaction["safe_text"] if key == "redact" else redaction["original_text"]
        sent = f'<div class="sitr-quote" dir="auto">{escape(shown)}</div>'
        if key == "private":
            sent += f'<div class="sitr-note">{t["private_note"]}</div>'
    sections = [
        seal(result, lang),
        f"<section><h4>{t['found_label']}</h4>{facts}{found}</section>",
        f"<section><h4>{t['sent_label']}</h4>{sent}</section>",
    ]
    if result["model_response"]:
        # The card already names the route, so the router's private-route tag is not repeated.
        answer = result["model_response"].removeprefix(router.PRIVATE_LABEL).strip()
        sections.append(
            f'<section><h4>{t["answer_label"]}</h4>'
            f'<div class="sitr-answer" dir="auto">{escape(answer)}</div></section>'
        )
    sections.append(technical_details(result, lang))
    return f'<div class="sitr-reply" dir="{_dir(lang)}">{"".join(sections)}</div>'


def technical_details(result: dict, lang: str = "en") -> str:
    t, analysis = TEXT[lang], result["analysis"]
    metadata = analysis["model_metadata"]
    rows = "".join(
        f"<tr><td>{e['entity_type']}</td><td>{e['severity']}</td><td>{e['source']}</td>"
        f"<td>{e['confidence']:.2f}</td><td>{e['page'] or '-'}</td></tr>"
        for e in analysis["entities"]
    )
    head = "".join(f"<th>{c}</th>" for c in t["columns"])
    table = f'<table class="sitr-table"><tr>{head}</tr>{rows}</table>' if rows else (
        f"<p>{t['no_findings']}</p>"
    )
    return (
        f"<details><summary>{t['details_label']}</summary>"
        f"<p>{t['reason_codes']}: {escape(', '.join(analysis['reason_codes']) or t['none'])}<br>"
        f"{t['detector_used']}: {escape(metadata['detector'])}<br>"
        f"{t['classifier_used']}: {escape(metadata['classifier'])}<br>"
        f"{t['time']}: {result['latency_ms']} ms</p>{table}</details>"
    )


def user_bubble(item: dict, lang: str = "en") -> str:
    t = TEXT[lang]
    task = dict(zip(TASK_VALUES, t["tasks"], strict=True)).get(item["task"], item["task"])
    meta = [f"{t['task_label']}: {task}"]
    if item["filename"]:
        meta.insert(0, f"{t['attached']}: {item['filename']}")
    text = f'<span dir="auto">{escape(item["text"])}</span>' if item["text"] else ""
    return (
        f'<div class="sitr-user">{text}<span class="meta" dir="{_dir(lang)}">'
        f"{escape(' · '.join(meta))}</span></div>"
    )


def messages(items: list[dict], lang: str = "en") -> list[dict]:
    """The whole conversation, rebuilt from what was sent and decided."""
    chat = []
    for item in items:
        chat.append({"role": "user", "content": user_bubble(item, lang)})
        content = (
            f'<div class="sitr-pending">{TEXT[lang]["pending"]}</div>'
            if item["result"] is None else reply(item["result"], lang)
        )
        chat.append({"role": "assistant", "content": content})
    return chat


def record(result: dict) -> None:
    with _stats_lock:
        _stats[_decision(result)] += 1
        _entity_stats.update(entity["entity_type"] for entity in result["analysis"]["entities"])


def dashboard(lang: str = "en") -> str:
    t = TEXT[lang]
    with _stats_lock:
        stats, entities = Counter(_stats), Counter(_entity_stats)
    total = sum(stats.values())
    if not total:
        return f'<p dir="{_dir(lang)}">{t["dashboard_empty"]}</p>'
    names = t["decisions"]
    bar = "".join(
        f'<span style="width:{stats[a] / total * 100:.2f}%;background:var(--sitr-{a})" '
        f'title="{names[a]}: {stats[a]}"></span>'
        for a in ACTION_ORDER if stats[a]
    )
    legend = "".join(
        f'<span><i style="background:var(--sitr-{a})"></i>{names[a]}<b>{stats[a]}</b></span>'
        for a in ACTION_ORDER
    )
    rows = "".join(
        f"<tr><td>{escape(kind)}</td><td>{n}</td></tr>" for kind, n in entities.most_common()
    )
    table = (
        f'<table class="sitr-table"><tr><th>{t["found"]}</th><th>{t["times"]}</th></tr>'
        f"{rows}</table>"
        if rows else f"<p>{t['nothing_found_yet']}</p>"
    )
    return (
        f'<div dir="{_dir(lang)}"><p><b>{total}</b> {t["inspected"]}</p>'
        f'<div class="sitr-bar" role="img" aria-label="{t["tab_dashboard"]}">{bar}</div>'
        f'<div class="sitr-legend">{legend}</div>{table}</div>'
    )


def readiness(lang: str = "en") -> str:
    """Whether each model is ready, for the header."""
    t = TEXT[lang]
    parts = []
    for name, module in ((t["detector"], hf_detection), (t["classifier"], risk_classifier)):
        state = module.status()["state"]
        css = "ready" if state == "ready" else "down" if state == "unavailable" else ""
        parts.append(f'<span class="{css}">{name} {t["states"].get(state, state)}</span>')
    return f'<div class="sitr-ready">{"".join(parts)}</div>'


def header(lang: str = "en") -> str:
    t = TEXT[lang]
    return (
        f'<div id="sitr-header" dir="{_dir(lang)}"><div class="sitr-wordmark">'
        f'<span class="ar" lang="ar">سِتر</span><span class="en">{t["product"]}</span></div>'
        f'<p class="sitr-purpose">{t["purpose"]}</p>{readiness(lang)}</div>'
    )


def empty_chat(lang: str = "en") -> str:
    t = TEXT[lang]
    return (
        f'<div class="sitr-empty" dir="{_dir(lang)}"><div class="ar" lang="ar">سِتر</div>'
        f"<h3>{t['empty_title']}</h3><p>{t['empty_hint']}</p></div>"
    )


def chat_examples(lang: str = "en") -> list[dict]:
    return [
        {"text": text, "display_text": label}
        for label, text in zip(TEXT[lang]["examples"], EXAMPLES.values(), strict=True)
    ]


def send(message: dict | None, task: str, items: list[dict], lang: str = "en"):
    """Show the message at once, then Sitr's reply when the inspection finishes."""
    message = message or {}
    text = (message.get("text") or "").strip()
    files = message.get("files") or []
    path = files[0] if files else None
    if isinstance(path, dict):
        path = path.get("path")
    if not text and not path:
        yield messages(items, lang), gr.MultimodalTextbox(), items, dashboard(lang)
        return
    item = {"text": text, "filename": Path(path).name if path else None,
            "task": task or "summarize", "result": None}
    pending = [*items, item]
    yield messages(pending, lang), gr.MultimodalTextbox(value=None, interactive=False), items, \
        dashboard(lang)
    # Uploads are Gradio temp copies; Sitr deletes them once inspected, even on failure.
    item["result"] = inspect_and_process(
        text=text or None, file_path=path, user_intent=item["task"], delete_file=bool(path)
    )
    record(item["result"])
    yield messages(pending, lang), gr.MultimodalTextbox(value=None, interactive=True), pending, \
        dashboard(lang)


def send_example(evt: gr.SelectData, items: list[dict], lang: str = "en"):
    index = list(EXAMPLES.values()).index(evt.value["text"])
    yield from send({"text": evt.value["text"]}, EXAMPLE_TASKS[index], items, lang)


def switch_language(lang: str, items: list[dict]) -> tuple:
    """Show every label, and the whole conversation, in the other language."""
    new = "ar" if lang == "en" else "en"
    t = TEXT[new]
    return (
        new,
        gr.Button(value=t["switch"]),
        header(new),
        gr.Tab(label=t["tab_inspect"]),
        gr.Tab(label=t["tab_dashboard"]),
        gr.Tab(label=t["tab_how"]),
        gr.Chatbot(value=messages(items, new), placeholder=empty_chat(new),
                   examples=chat_examples(new), rtl=new == "ar"),
        gr.MultimodalTextbox(placeholder=t["placeholder"], rtl=new == "ar"),
        gr.Dropdown(choices=list(zip(t["tasks"], TASK_VALUES, strict=True)),
                    label=t["task_label"]),
        t["dashboard_intro"],
        dashboard(new),
        gr.Button(value=t["refresh"]),
        t["how"],
    )


def enable_audit_log() -> None:
    """Write Sitr's metadata-only audit events to the console. Safe to call twice."""
    logger = logging.getLogger("sitr")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())


def warm_up() -> None:
    """Load every model in the background, then run each detector once.

    A message that arrives before the privacy detector is ready is blocked, so the demo should
    wait until the header says ready.
    """
    for module in (hf_detection, risk_classifier, router):
        module.warm_up()

    def first_run() -> None:
        hf_detection.detect_entities("Warm-up for a public notice.")
        risk_classifier.classify_risk("Warm-up for a public notice.")

    threading.Thread(target=first_run, daemon=True).start()


EN = TEXT["en"]
with gr.Blocks(title="Sitr AI Gate", delete_cache=CACHE_PURGE_SECONDS) as demo:
    lang_state = gr.State("en")
    conversation = gr.State([])
    with gr.Row(elem_id="sitr-top"):
        header_output = gr.HTML(header())
        lang_button = gr.Button(EN["switch"], size="sm", variant="secondary", elem_id="sitr-lang")
    with gr.Tab(EN["tab_inspect"]) as inspect_tab:
        chat = gr.Chatbot(
            elem_id="sitr-chat", show_label=False, height="62vh", min_height=360,
            placeholder=empty_chat(), examples=chat_examples(), sanitize_html=False,
            render_markdown=False, layout="bubble", autoscroll=True, buttons=["copy"],
        )
        with gr.Row(elem_id="sitr-tools"):
            task_input = gr.Dropdown(
                TASKS, value="answer the request", label=EN["task_label"], show_label=False,
                container=False, elem_id="sitr-task",
            )
        composer = gr.MultimodalTextbox(
            placeholder=EN["placeholder"], show_label=False, file_count="single",
            file_types=[".pdf", ".txt", ".md", ".csv", ".py", ".js", ".ts", ".java", ".json",
                        ".yml", ".yaml", ".env", ".sql", ".sh"],
            sources=["upload"], elem_id="sitr-composer", autofocus=True,
        )
    with gr.Tab(EN["tab_dashboard"]) as dashboard_tab:
        dashboard_intro = gr.Markdown(EN["dashboard_intro"])
        dashboard_output = gr.HTML(dashboard())
        refresh_button = gr.Button(EN["refresh"], size="sm")
        refresh_button.click(dashboard, lang_state, dashboard_output)
    with gr.Tab(EN["tab_how"]) as how_tab:
        how_output = gr.Markdown(EN["how"])

    outputs = [chat, composer, conversation, dashboard_output]
    composer.submit(send, [composer, task_input, conversation, lang_state], outputs)
    chat.example_select(send_example, [conversation, lang_state], outputs)
    # The trash icon starts a new conversation, so the remembered one is cleared too.
    chat.clear(lambda: [], None, conversation)
    lang_button.click(
        switch_language, [lang_state, conversation],
        [lang_state, lang_button, header_output, inspect_tab, dashboard_tab, how_tab, chat,
         composer, task_input, dashboard_intro, dashboard_output, refresh_button, how_output],
    ).then(None, lang_button, js=SET_DIRECTION_JS)
    gr.Timer(5).tick(header, lang_state, header_output)
    demo.load(header, lang_state, header_output)

if __name__ == "__main__":
    enable_audit_log()
    warm_up()
    demo.launch(theme=THEME, css=CSS, head=HEAD, footer_links=[])
