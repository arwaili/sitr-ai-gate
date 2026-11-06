"""Sitr Gradio interface. All security decisions come from inspect_and_process."""

import logging
import threading
from collections import Counter
from html import escape

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

# A fixed list, so free text can never reach a model through the task field.
TASK_VALUES = [
    "summarize", "answer the request", "rewrite professionally", "translate to English",
    "translate to Arabic",
]
TASKS = list(zip(TEXT["en"]["tasks"], TASK_VALUES, strict=True))

# The Arabic word on the seal in both languages' Arabic mode; English mode uses TEXT names.
SEAL_WORDS_AR = {"allow": "مسموح", "redact": "منقّح", "private": "خاص", "block": "محظور",
                 "error": "لم يُفحص"}
ACTION_ORDER = ("allow", "redact", "private", "block", "error")
# Findings are colored by how serious they are, matching the seal colors.
_SEVERITY_TYPES = {
    "medium": ("PERSON", "EMAIL", "PHONE", "ADDRESS", "DATE_OF_BIRTH", "USERNAME"),
    "high": ("IBAN", "QATAR_ID", "PASSPORT", "ACCOUNT_NUMBER", "SALARY", "NATIONAL_ID",
             "CREDIT_CARD", "PIN", "INTERNAL_HOST"),
    "critical": ("API_KEY", "CLOUD_KEY", "PASSWORD", "DATABASE_URL", "PRIVATE_KEY", "JWT",
                 "BEARER_TOKEN"),
}
_SEVERITY_COLORS = {"medium": "#E9C48A", "high": "#9DBAD6", "critical": "#D88A9E"}
COLOR_MAP = {kind: _SEVERITY_COLORS[s] for s, kinds in _SEVERITY_TYPES.items() for kind in kinds}

# Uploads are stored by Gradio on drop, so one that is never inspected is purged on this schedule.
CACHE_PURGE_SECONDS = (600, 600)

THEME = gr.themes.Base(
    font=[gr.themes.GoogleFont("Readex Pro"), "system-ui", "sans-serif"],
    radius_size=gr.themes.sizes.radius_sm,
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
    input_background_fill="#F8FAF9",
    input_background_fill_dark="#141C1A",
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
}}
.dark {{
  --sitr-allow: #5FB48D; --sitr-redact: #E0A24E; --sitr-private: #7FA8D2;
  --sitr-block: #E0708F; --sitr-error: #9DB0AA; --sitr-muted: #9DB0AA;
}}
.gradio-container {{ max-width: 1180px !important; margin: 0 auto; }}
#sitr-top {{
  gap: 0; border-radius: 6px; padding: 0 4px 0 0;
  background: url("{_LATTICE}") repeat; border-bottom: 3px solid var(--sitr-block);
}}
#sitr-header {{
  display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
  gap: 12px 32px; padding: 24px 24px 20px;
}}
.sitr-wordmark {{ display: flex; align-items: baseline; gap: 14px; }}
.sitr-wordmark .ar {{
  font-family: "Reem Kufi", "Readex Pro", sans-serif; font-weight: 700;
  font-size: 3.4rem; line-height: 1; color: var(--sitr-block);
}}
.sitr-wordmark .en {{ font-size: 1.15rem; font-weight: 600; }}
.sitr-purpose {{ margin: 10px 0 0; max-width: 60ch; color: var(--sitr-muted); }}
.sitr-ready {{ display: flex; flex-direction: column; gap: 4px; font-size: .9rem; }}
.sitr-ready span::before {{
  content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  margin-inline-end: 8px; background: var(--sitr-redact);
}}
.sitr-ready span.ready::before {{ background: var(--sitr-allow); }}
.sitr-ready span.down::before {{ background: var(--sitr-block); }}
#sitr-top {{ position: relative; }}
#sitr-lang {{ position: absolute !important; top: 18px; inset-inline-end: 18px; z-index: 1;
  width: auto !important; min-width: 96px; height: auto !important; margin: 0; }}
button[role="tab"].selected, button[role="tab"][aria-selected="true"] {{
  color: var(--sitr-block) !important; border-color: var(--sitr-block) !important;
}}

.sitr-panel {{ background: var(--block-background-fill) !important; padding: 4px; }}
.sitr-panel > div {{ border: 0 !important; }}
.sitr-hint {{ padding: 10px 12px 2px; color: var(--sitr-muted); font-size: .9rem; }}
.sitr-panel .html-container, .sitr-panel .block, #sitr-examples {{
  background: var(--block-background-fill) !important; }}
#sitr-file {{ border: 1px dashed #A9B6B1 !important; }}
/* Gradio stamps dir="ltr" on every block; in Arabic mode the page direction wins. */
/* The findings view sets its own direction from the text, so it is left alone. */
html[dir="rtl"] .gradio-container [dir="ltr"]:not(#sitr-found, #sitr-found *) {{
  direction: rtl; }}
#sitr-examples {{ display: grid !important; grid-template-columns: repeat(4, 1fr);
  gap: 8px; padding: 6px 12px 12px; }}
#sitr-examples button {{ min-width: 0; white-space: normal; }}
@media (max-width: 900px) {{ #sitr-examples {{ grid-template-columns: repeat(2, 1fr); }} }}

.sitr-seal {{
  border: 2px solid var(--seal); border-inline-start-width: 10px; border-radius: 6px;
  padding: 22px 24px 20px; margin: 10px;
}}
.sitr-seal .word {{
  font-family: "Reem Kufi", "Readex Pro", sans-serif; font-weight: 700; font-size: 3rem;
  line-height: 1.15; color: var(--seal);
}}
.sitr-seal .word.latin {{ font-family: inherit; font-size: 2.4rem; letter-spacing: -.01em; }}
.sitr-seal .what {{ margin-top: 10px; max-width: 56ch; }}
.sitr-seal.allow {{ --seal: var(--sitr-allow); }}
.sitr-seal.redact {{ --seal: var(--sitr-redact); }}
.sitr-seal.private {{ --seal: var(--sitr-private); }}
.sitr-seal.block {{ --seal: var(--sitr-block); }}
.sitr-seal.error {{ --seal: var(--sitr-error); }}
.sitr-seal.empty {{ --seal: var(--border-color-primary); color: var(--sitr-muted); }}
.sitr-seal.empty .word {{ font-family: inherit; font-size: 1.3rem; font-weight: 600;
  color: inherit; }}
@media (prefers-reduced-motion: no-preference) {{
  .sitr-seal:not(.empty) {{ animation: sitr-stamp .28s ease-out; }}
  @keyframes sitr-stamp {{ from {{ transform: scale(1.03); opacity: 0; }} }}
}}
.sitr-facts dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px;
  margin: 0; padding: 4px 16px 14px; }}
.sitr-facts dt {{ color: var(--sitr-muted); }}
.sitr-facts dd {{ margin: 0; }}
.sitr-text textarea, .sitr-text .textfield {{
  unicode-bidi: plaintext; text-align: start; white-space: pre-wrap;
}}
.sitr-bar {{ display: flex; height: 28px; border-radius: 4px; overflow: hidden;
  background: var(--border-color-primary); }}
.sitr-bar span {{ display: block; }}
.sitr-legend {{ display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 12px 0 20px; }}
.sitr-legend b {{ font-size: 1.4rem; margin-inline-start: 6px; }}
.sitr-legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-inline-end: 6px; }}
.sitr-table {{ border-collapse: collapse; min-width: 260px; }}
.sitr-table td, .sitr-table th {{ padding: 6px 14px; text-align: start;
  border-bottom: 1px solid var(--border-color-primary); }}
@media (max-width: 640px) {{
  #sitr-header {{ padding: 64px 14px 16px; }}
  .sitr-wordmark .ar {{ font-size: 2.6rem; }}
  .sitr-seal .word {{ font-size: 2.4rem; }}
  .sitr-seal .word.latin {{ font-size: 2rem; }}
}}
"""

# On a phone the decision sits below the inputs, so bring it into view once it is shown.
SHOW_DECISION_JS = """() => { if (window.innerWidth < 900) document.querySelector(".sitr-seal")
  ?.scrollIntoView({block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)")
  .matches ? "auto" : "smooth"}); }"""
# Arabic reads right to left, so the whole page flips with the language. State never reaches
# the browser, so this reads the switch button, which offers "English" only while in Arabic.
SET_DIRECTION_JS = """(label) => { const ar = label === "English";
  document.documentElement.lang = ar ? "ar" : "en";
  document.documentElement.dir = ar ? "rtl" : "ltr"; }"""

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
    return "؀" <= first <= "ۿ"


def entity_counts(entities: list[dict], lang: str = "en") -> str:
    counts = Counter(entity["entity_type"] for entity in entities)
    joiner = "، " if lang == "ar" else ", "
    return joiner.join(f"{kind} × {n}" for kind, n in counts.most_common()) or TEXT[lang][
        "nothing"
    ]


def _decision(result: dict) -> str:
    return "error" if result["status"] == "error" else result["action_taken"]


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


def empty_seal(lang: str = "en") -> str:
    t = TEXT[lang]
    return (
        f'<div class="sitr-seal empty"><div class="word">{t["empty_title"]}</div>'
        f'<div class="what">{t["empty_hint"]}</div></div>'
    )


def render(result: dict, lang: str = "en") -> tuple[str, str, list, str, str, str]:
    """Convert a FinalResponse dict into the values of the result components."""
    t, analysis, key = TEXT[lang], result["analysis"], _decision(result)
    risk = t["not_assessed"] if key == "error" else (
        f"{t['risk_levels'][analysis['risk_level']]}{'، ' if lang == 'ar' else ', '}"
        + t["of_100"].format(score=analysis["risk_score"])
    )
    facts = (
        f'<div class="sitr-facts"><dl><dt>{t["risk"]}</dt><dd>{escape(risk)}</dd>'
        f"<dt>{t['found']}</dt><dd>{escape(entity_counts(analysis['entities'], lang))}</dd>"
        f"<dt>{t['sent_to']}</dt><dd>{escape(t['routes'][key])}</dd></dl></div>"
    )
    redaction = result["redaction"]
    original = highlight(redaction["original_text"], analysis["entities"]) if redaction else []
    # On block nothing is sent, so the redacted text would wrongly suggest something was.
    sent = redaction["safe_text"] if redaction and key not in ("block", "error") else (
        t["nothing_sent"]
    )
    # The seal already names the route, so the router's private-route tag is not repeated.
    answer = (result["model_response"] or t["no_model"]).removeprefix(router.PRIVATE_LABEL)
    metadata = analysis["model_metadata"]
    rows = "\n".join(
        f"| {e['entity_type']} | {e['severity']} | {e['source']} | {e['confidence']:.2f} "
        f"| {e['page'] or '-'} |"
        for e in analysis["entities"]
    )
    columns = " | ".join(t["columns"])
    details = (
        f"**{t['reason_codes']}:** {', '.join(analysis['reason_codes']) or t['none']}\n\n"
        f"**{t['detector_used']}:** `{metadata['detector']}`\n\n"
        f"**{t['classifier_used']}:** `{metadata['classifier']}`\n\n"
        f"**{t['time']}:** {result['latency_ms']} ms\n\n"
        + (f"| {columns} |\n|---|---|---|---|---|\n{rows}" if rows else t["no_findings"])
    )
    return seal(result, lang), facts, original, sent, answer.lstrip(), details


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
        return f"<p>{t['dashboard_empty']}</p>"
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
        f"<p><b>{total}</b> {t['inspected']}</p>"
        f'<div class="sitr-bar" role="img" aria-label="{t["tab_dashboard"]}">{bar}</div>'
        f'<div class="sitr-legend">{legend}</div>{table}'
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
        '<div id="sitr-header"><div><div class="sitr-wordmark">'
        f'<span class="ar" lang="ar">سِتر</span><span class="en">{t["product"]}</span></div>'
        f'<p class="sitr-purpose">{t["purpose"]}</p></div>{readiness(lang)}</div>'
    )


def analyze(text: str, file_path: str | None, task: str, lang: str = "en") -> tuple:
    # Uploads are Gradio temp copies; Sitr deletes them once inspected, even on failure, and
    # the None at the end clears the file box so it never points at a deleted file.
    result = inspect_and_process(
        text=text or None, file_path=file_path, user_intent=task or "summarize",
        delete_file=bool(file_path),
    )
    record(result)
    return (*_result_view(result, lang), dashboard(lang), header(lang), None, result)


def _result_view(result: dict | None, lang: str) -> tuple:
    t = TEXT[lang]
    if result is None:
        return (empty_seal(lang), "", gr.HighlightedText(value=[], label=t["found_label"]),
                "", "", "")
    seal_html, facts, original, sent, answer, details = render(result, lang)
    rtl = bool(result["redaction"]) and starts_rtl(result["redaction"]["original_text"])
    # The highlighted view is a row of separate segments, so its direction is set as a whole.
    original = gr.HighlightedText(value=original, rtl=rtl, label=t["found_label"])
    return seal_html, facts, original, sent, answer, details


def switch_language(lang: str, last: dict | None) -> tuple:
    """Show every label, and the last result, in the other language."""
    new = "ar" if lang == "en" else "en"
    t = TEXT[new]
    seal_html, facts, original, sent, answer, details = _result_view(last, new)
    return (
        new,
        gr.Button(value=t["switch"]),
        header(new),
        gr.Tab(label=t["tab_inspect"]),
        gr.Tab(label=t["tab_dashboard"]),
        gr.Tab(label=t["tab_how"]),
        f'<div class="sitr-hint">{t["examples_label"]}</div>',
        *(gr.Button(value=label) for label in t["examples"]),
        gr.Textbox(label=t["text_label"], placeholder=t["text_placeholder"]),
        gr.File(label=t["file_label"]),
        gr.Dropdown(choices=list(zip(t["tasks"], TASK_VALUES, strict=True)), label=t["task_label"]),
        gr.Button(value=t["inspect"]),
        seal_html,
        facts,
        gr.Textbox(value=answer, label=t["answer_label"]),
        original,
        gr.Textbox(value=sent, label=t["sent_label"]),
        gr.Accordion(label=t["details_label"]),
        details,
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

    A request that arrives before the privacy detector is ready is blocked, so the demo should
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
    last_result = gr.State(None)
    with gr.Row(elem_id="sitr-top"):
        header_output = gr.HTML(header(), scale=10)
        lang_button = gr.Button(
            EN["switch"], size="sm", variant="secondary", scale=0, elem_id="sitr-lang"
        )
    with gr.Tab(EN["tab_inspect"]) as inspect_tab:
        with gr.Row(equal_height=False):
            with gr.Column(scale=5), gr.Group(elem_classes="sitr-panel"):
                examples_label = gr.HTML(f'<div class="sitr-hint">{EN["examples_label"]}</div>')
                with gr.Row(elem_id="sitr-examples"):
                    example_buttons = [
                        gr.Button(label, size="sm", variant="secondary")
                        for label in EN["examples"]
                    ]
                text_input = gr.Textbox(
                    lines=7, label=EN["text_label"], placeholder=EN["text_placeholder"],
                    elem_classes="sitr-text",
                )
                file_input = gr.File(
                    label=EN["file_label"], type="filepath", height=130, elem_id="sitr-file"
                )
                with gr.Row(equal_height=True):
                    task_input = gr.Dropdown(TASKS, value="summarize", label=EN["task_label"],
                                             scale=3)
                    submit = gr.Button(EN["inspect"], variant="primary", size="lg", scale=2)
            with gr.Column(scale=6), gr.Group(elem_classes="sitr-panel"):
                seal_output = gr.HTML(empty_seal())
                facts_output = gr.HTML()
                response_output = gr.Textbox(
                    label=EN["answer_label"], lines=5, elem_classes="sitr-text"
                )
        with gr.Row():
            original_output = gr.HighlightedText(
                label=EN["found_label"], color_map=COLOR_MAP, show_legend=False,
                elem_classes="sitr-text", elem_id="sitr-found",
            )
            safe_output = gr.Textbox(label=EN["sent_label"], lines=7, elem_classes="sitr-text")
        with gr.Accordion(EN["details_label"], open=False) as details_box:
            details_output = gr.Markdown()
    with gr.Tab(EN["tab_dashboard"]) as dashboard_tab:
        dashboard_intro = gr.Markdown(EN["dashboard_intro"])
        dashboard_output = gr.HTML(dashboard())
        refresh_button = gr.Button(EN["refresh"], size="sm")
        refresh_button.click(dashboard, lang_state, dashboard_output)
    with gr.Tab(EN["tab_how"]) as how_tab:
        how_output = gr.Markdown(EN["how"])

    outputs = [seal_output, facts_output, original_output, safe_output, response_output,
               details_output, dashboard_output, header_output, file_input, last_result]
    for button, text in zip(example_buttons, EXAMPLES.values(), strict=True):
        button.click(lambda text=text: text, None, text_input).then(
            lambda text, task, lang: analyze(text, None, task, lang),
            [text_input, task_input, lang_state], outputs,
        ).then(None, js=SHOW_DECISION_JS)
    submit.click(analyze, [text_input, file_input, task_input, lang_state], outputs).then(
        None, js=SHOW_DECISION_JS
    )
    lang_button.click(
        switch_language, [lang_state, last_result],
        [lang_state, lang_button, header_output, inspect_tab, dashboard_tab, how_tab,
         examples_label, *example_buttons, text_input, file_input, task_input, submit,
         seal_output, facts_output, response_output, original_output, safe_output,
         details_box, details_output, dashboard_intro, dashboard_output, refresh_button,
         how_output],
    ).then(None, lang_button, js=SET_DIRECTION_JS)
    gr.Timer(5).tick(header, lang_state, header_output)
    demo.load(header, lang_state, header_output)

if __name__ == "__main__":
    enable_audit_log()
    warm_up()
    demo.launch(theme=THEME, css=CSS, head=HEAD)
