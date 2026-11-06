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
from src.contracts import RedactionResult
from src.export import redacted_pdf, redacted_text_file
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

MAROON = "#8A1538"
THEME = gr.themes.Base(
    font=[gr.themes.GoogleFont("Readex Pro"), "system-ui", "sans-serif"],
    radius_size=gr.themes.sizes.radius_md,
).set(
    body_background_fill="#FFFFFF",
    body_background_fill_dark="#0E0E0F",
    body_text_color="#1B1718",
    body_text_color_dark="#ECECEC",
    block_background_fill="#FFFFFF",
    block_background_fill_dark="#18181A",
    block_border_color="#E8E3E4",
    block_border_color_dark="#2C2C30",
    border_color_primary="#E8E3E4",
    border_color_primary_dark="#2C2C30",
    input_background_fill="#FFFFFF",
    input_background_fill_dark="#1C1C1F",
    block_label_text_color="#5E5A5B",
    block_label_text_color_dark="#A3A3A8",
    color_accent=MAROON,
    color_accent_soft="#F6E8EC",
    color_accent_soft_dark="#3A1220",
    button_primary_background_fill=MAROON,
    button_primary_background_fill_hover="#6F102D",
    button_primary_background_fill_dark=MAROON,
    button_primary_background_fill_hover_dark="#A01A43",
    button_primary_text_color="#FFFFFF",
    button_primary_text_color_dark="#FFFFFF",
    button_secondary_background_fill="#FFFFFF",
    button_secondary_background_fill_dark="#1C1C1F",
    button_secondary_border_color="#E2DCDD",
    button_secondary_border_color_dark="#323236",
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
  --sitr-maroon: #8A1538; --sitr-side: #FAF7F8;
  --sitr-allow: #2F7A5B; --sitr-redact: #A8661B; --sitr-private: #24527A;
  --sitr-block: #8A1538; --sitr-error: #6B6566; --sitr-muted: #5E5A5B;
  --sitr-medium: #F3DDB4; --sitr-high: #D3E1EE; --sitr-critical: #F1D0D9;
}}
/* Dark keeps the same maroon on near-black, with dark grey panels. */
.dark {{
  --sitr-side: #141416;
  --sitr-allow: #5FB48D; --sitr-redact: #E0A24E; --sitr-private: #7FA8D2;
  --sitr-block: #8A1538; --sitr-error: #A3A3A8; --sitr-muted: #A3A3A8;
  --sitr-medium: #5A4220; --sitr-high: #233A52; --sitr-critical: #4A1424;
}}
/* A full-page app: a sidebar for navigation and a centered reading column, like a chat app. */
.gradio-container {{ max-width: none !important; width: 100% !important; }}
footer {{ display: none !important; }}
/* The chat scrolls across the whole main area (scrollbar at the window's edge); the
   messages, composer and other pages keep a centered reading width. */
@media (min-width: 769px) {{
  .gradio-container > .main.fillable {{ max-width: none !important; padding-right: 0 !important; }}
}}
.sitr-copy {{ white-space: nowrap; }}
#sitr-main {{ width: 100%; padding: 0; }}
#sitr-main > .column > :not(#sitr-chat) {{ width: 100%; max-width: 900px; margin-inline: auto; }}
#sitr-chat .message-wrap {{ max-width: 900px; margin: 0 auto !important; padding-inline: 16px; }}
.sitr-page-title {{ font-size: 1.6rem; font-weight: 600; margin: 18px 0 6px; }}
#sitr-sidebar {{ background: var(--sitr-side) !important;
  border-inline-end: 1px solid var(--border-color-primary); }}
#sitr-sidebar .sidebar-content {{ flex: 1 1 auto; display: flex; flex-direction: column; }}
#sitr-sidebar .sidebar-content > .column {{ flex: 1 1 auto; }}
.sitr-nav, #sitr-foot {{ flex: 0 0 auto !important; }}
#sitr-foot {{ margin-top: auto !important; gap: 10px !important; padding-top: 14px;
  border-top: 1px solid var(--border-color-primary); }}
#sitr-foot .block {{ background: transparent !important; border: 0 !important;
  box-shadow: none !important; padding: 0 !important; }}
.sitr-brand {{ position: relative; overflow: hidden; padding: 18px 16px 16px; border-radius: 14px;
  background: linear-gradient(180deg, rgba(138, 21, 56, .07), transparent 70%),
    url("{_LATTICE}") repeat;
  border: 1px solid var(--border-color-primary); }}
.sitr-brand .ar {{ display: block; font-family: "Reem Kufi", "Readex Pro", sans-serif;
  font-weight: 700; font-size: 2.6rem; line-height: 1; color: var(--sitr-maroon); }}
.sitr-brand .en {{ display: block; margin-top: 8px; font-weight: 600; font-size: .95rem; }}
.sitr-brand .tag {{ display: block; margin-top: 2px; font-size: .8rem; color: var(--sitr-muted); }}
.sitr-brand::after {{ content: ""; position: absolute; inset-inline: 16px; bottom: 0; height: 3px;
  border-radius: 3px 3px 0 0; background: var(--sitr-maroon); }}
#sitr-new {{ justify-content: flex-start !important; }}
.sitr-nav {{ gap: 2px !important; margin-top: 10px; }}
.sitr-nav button {{ justify-content: flex-start !important; text-align: start;
  border: 0 !important; box-shadow: none !important; background: transparent !important;
  color: var(--body-text-color) !important; font-weight: 500; }}
.sitr-nav button:hover {{ background: var(--border-color-primary) !important; }}
.sitr-nav button.primary {{ background: var(--color-accent-soft) !important;
  color: var(--sitr-maroon) !important; font-weight: 600; }}
.dark .sitr-nav button.primary {{ background: var(--sitr-maroon) !important;
  color: #FFFFFF !important; }}
.sitr-status h4 {{ margin: 0 0 6px; font-size: .76rem; font-weight: 600;
  color: var(--sitr-muted); }}
.sitr-models {{ display: flex; flex-direction: column; gap: 4px; font-size: .85rem; }}
.sitr-models span::before {{ content: ""; display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-inline-end: 7px; background: var(--sitr-redact); }}
.sitr-models span.ready::before {{ background: var(--sitr-allow); }}
.sitr-models span.down::before {{ background: var(--sitr-block); }}
#sitr-toggles {{ gap: 8px; }}
#sitr-toggles button {{ min-width: 0 !important; background: transparent !important;
  border: 1px solid var(--border-color-primary) !important; box-shadow: none !important; }}
#sitr-toggles button:hover {{ border-color: var(--sitr-maroon) !important; }}
#sitr-theme {{ flex: 0 0 44px !important; font-size: 1.1rem; }}

.sitr-kpis {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  margin: 10px 0 18px; }}
@media (max-width: 640px) {{ .sitr-kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
.sitr-kpi {{ border: 1px solid var(--border-color-primary); border-top: 4px solid var(--kpi);
  border-radius: 10px; padding: 12px 14px; background: var(--block-background-fill); }}
.sitr-kpi b {{ display: block; font-size: 1.9rem; line-height: 1.2; }}
.sitr-kpi span {{ color: var(--sitr-muted); font-size: .88rem; }}

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
.sitr-next {{ position: relative; border-radius: 10px; padding: 14px 16px;
  background: var(--block-background-fill); border: 1px solid var(--border-color-primary);
  border-inline-start: 4px solid var(--seal-next, var(--sitr-muted)); }}
.sitr-next h3 {{ margin: 0 0 4px; font-size: 1.05rem; }}
.sitr-next p {{ margin: 0 0 10px; }}
.sitr-next.allow {{ --seal-next: var(--sitr-allow); }}
.sitr-next.redact {{ --seal-next: var(--sitr-redact); }}
.sitr-next.private {{ --seal-next: var(--sitr-private); }}
.sitr-next.block {{ --seal-next: var(--sitr-block); }}
.sitr-copy {{ position: absolute; top: 12px; inset-inline-end: 12px; padding: 4px 12px;
  border-radius: 999px; border: 1px solid var(--border-color-primary); cursor: pointer;
  background: var(--body-background-fill); color: var(--body-text-color); font: inherit;
  font-size: .82rem; }}
.sitr-files p {{ margin: 6px 0 0; color: var(--sitr-muted); font-size: .88rem; }}
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
/* Claude-style conversation: Sitr's replies sit on the page with no bubble, the user's
   messages are small right-aligned bubbles, and the type is set at reading size. */
:root {{ --sitr-user-bubble: #F4ECEE; }}
.dark {{ --sitr-user-bubble: #232326; }}
#sitr-chat, #sitr-chat .bubble-wrap, #sitr-chat .message-wrap {{
  background: transparent !important; }}
#sitr-chat .message-row {{ margin: 6px 0 !important; }}
/* The new-chat icon floats over the conversation, so it sits on the page color. */
#sitr-chat .icon-button-wrapper, #sitr-chat .top-panel {{
  background: var(--body-background-fill) !important; border-radius: 8px; }}
#sitr-chat .message {{ font-size: .95rem !important; line-height: 1.6 !important; }}
#sitr-chat .bot-row .message {{ background: transparent !important; border: 0 !important;
  box-shadow: none !important; padding: 4px 0 !important; width: 100% !important;
  max-width: 100% !important; }}
#sitr-chat .user-row .message {{ background: var(--sitr-user-bubble) !important;
  border: 0 !important; box-shadow: none !important; border-radius: 18px !important;
  padding: 10px 14px !important; width: fit-content !important;
  max-width: min(78%, 560px) !important; }}
#sitr-chat .user-row .flex-wrap {{ width: auto !important; max-width: 100% !important;
  align-items: flex-end !important; }}
.sitr-user {{ overflow-wrap: break-word; word-break: normal; }}
#sitr-chat .user-row {{ justify-content: flex-end !important; }}
#sitr-chat .bot-row, #sitr-chat .bot-row .flex-wrap {{ width: 100% !important;
  max-width: 100% !important; }}
#sitr-chat .bot-row {{ justify-content: flex-start !important; }}
.sitr-reply {{ gap: 12px !important; }}
.sitr-seal {{ padding: 10px 14px !important; border-width: 1px !important;
  border-inline-start-width: 4px !important; }}
.sitr-seal .word {{ font-size: 1.55rem !important; }}
.sitr-seal .word.latin {{ font-size: 1.2rem !important; font-weight: 600 !important; }}
.sitr-seal .what {{ font-size: .92rem; }}
.sitr-next {{ padding: 12px 14px !important; }}
.sitr-next h3 {{ font-size: .98rem !important; }}
.sitr-next p, .sitr-facts, .sitr-answer {{ font-size: .92rem; }}
.sitr-quote {{ font-size: .9rem; line-height: 1.65 !important; padding: 8px 12px !important; }}
.sitr-reply h4 {{ font-size: .78rem !important; }}
.sitr-user .meta {{ font-size: .76rem !important; }}
.sitr-empty .ar {{ font-size: 2.6rem !important; }}
.sitr-empty h3 {{ font-size: 1.1rem !important; }}
/* A size smaller throughout the conversation. */
#sitr-chat .message {{ font-size: .88rem !important; line-height: 1.55 !important; }}
#sitr-chat .sitr-headline {{ font-size: .98rem; }}
#sitr-chat .sitr-quote {{ font-size: .84rem; }}
#sitr-chat .user-row .message {{ padding: 8px 13px !important; }}
#sitr-chat .examples button {{ font-size: .84rem !important; }}
#sitr-composer textarea {{ font-size: .9rem !important; }}

/* The answer card: a status chip, a yes or no headline, why, and the version to use. */
.sitr-chip {{ align-self: flex-start; display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600;
  color: var(--chip); background: color-mix(in srgb, var(--chip) 13%, transparent); }}
.sitr-chip::before {{ content: ""; width: 7px; height: 7px; border-radius: 50%;
  background: var(--chip); }}
.sitr-chip.allow {{ --chip: var(--sitr-allow); }}
.sitr-chip.redact {{ --chip: var(--sitr-redact); }}
.sitr-chip.private {{ --chip: var(--sitr-private); }}
.sitr-chip.block {{ --chip: var(--sitr-block); }}
.dark .sitr-chip.block {{ background: var(--sitr-maroon); color: #FFFFFF; }}
.dark .sitr-chip.block::before {{ background: #FFFFFF; }}
.sitr-chip.error {{ --chip: var(--sitr-error); }}
.sitr-headline {{ margin: 0 !important; font-size: 1.05rem; font-weight: 600; }}
.sitr-why {{ margin: 0 !important; color: var(--body-text-color); }}
.sitr-ready {{ border: 1px solid var(--border-color-primary); border-radius: 12px;
  overflow: hidden; background: var(--block-background-fill); }}
.sitr-ready-head {{ display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 6px 8px 6px 12px; font-size: .8rem; color: var(--sitr-muted);
  border-bottom: 1px solid var(--border-color-primary); }}
html[dir="rtl"] .sitr-ready-head {{ padding: 6px 12px 6px 8px; }}
.sitr-ready .sitr-quote {{ border: 0 !important; border-radius: 0 !important;
  background: transparent !important; max-height: 280px; overflow: auto; }}
.sitr-copy {{ position: static !important; }}
.sitr-more summary {{ cursor: pointer; color: var(--sitr-muted); font-size: .85rem; }}
.sitr-more[open] summary {{ margin-bottom: 8px; }}
.sitr-more .sitr-quote {{ margin-bottom: 10px; }}
.sitr-tech h4 {{ margin: 6px 0 4px; }}
.sitr-tech p {{ margin: 0; font-size: .82rem; color: var(--sitr-muted); }}

/* Four suggestions as an even 2 x 2 grid; replies keep clear of the chat's scrollbar; the
   user's bubble is wide enough for an email address on one line. */
#sitr-chat .examples {{ grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  max-width: 620px; margin: 0 auto; }}
#sitr-chat .bot-row .message {{ padding-inline-end: 14px !important; }}
#sitr-chat .user-row .message {{ min-width: min(340px, 72vw) !important; }}
.sitr-user {{ overflow-wrap: anywhere; }}

/* Composer: the +, the text and the send arrow share one centered line. */
#sitr-composer {{ border: 1px solid var(--border-color-primary) !important;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04) !important; padding: 6px 8px !important; }}
#sitr-composer .input-row {{ align-items: center !important; gap: 8px !important; }}
#sitr-composer .upload-button, #sitr-composer .submit-button {{ flex: 0 0 34px !important;
  margin: 0 !important; align-self: center !important; }}
#sitr-composer .upload-button::before {{ display: block; transform: translateY(-1px); }}
#sitr-composer .textarea-wrapper {{ display: flex !important; align-items: center !important;
  flex: 1 1 auto !important; }}
#sitr-composer textarea {{ padding: 6px 2px !important; line-height: 1.5 !important;
  font-size: .95rem !important; min-height: 0 !important; }}
#sitr-tools {{ max-width: 100%; }}
#sitr-task {{ width: 230px !important; font-size: .88rem; }}

/* Gradio stamps dir="ltr" on every block; in Arabic mode the page direction wins. */
html[dir="rtl"] .gradio-container [dir="ltr"] {{ direction: rtl; }}
"""

# Arabic reads right to left, so the whole page flips with the language. State never reaches
# the browser, so this reads the switch button, which offers "English" only while in Arabic.
SET_DIRECTION_JS = """(label) => { const ar = label === "English";
  document.documentElement.lang = ar ? "ar" : "en";
  document.documentElement.dir = ar ? "rtl" : "ltr"; }"""

# Light or dark: Gradio marks dark mode with a class on <body>; the choice is remembered in this
# browser only, and the button shows the mode it switches to.
THEME_TOGGLE_JS = """() => { const dark = document.body.classList.toggle("dark");
  try { localStorage.setItem("sitr-theme", dark ? "dark" : "light"); } catch (e) {}
  return dark ? "☀" : "☾"; }"""
THEME_LOAD_JS = """() => { let saved = null;
  try { saved = localStorage.getItem("sitr-theme"); } catch (e) {}
  if (saved) document.body.classList.toggle("dark", saved === "dark");
  return document.body.classList.contains("dark") ? "☀" : "☾"; }"""
# On a phone the sidebar covers the chat, so it starts closed and closes after each choice.
CLOSE_SIDEBAR_ON_PHONE_JS = """() => { const s = document.querySelector("#sitr-sidebar");
  if (window.innerWidth < 900 && s && s.classList.contains("open"))
    (s.querySelector(".toggle-button") || s.parentElement.querySelector(".toggle-button"))
      ?.click(); }"""
PAGES = ("chat", "dashboard", "how")

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


# Where the user plans to send it, named in the answer when the question mentions it.
DESTINATIONS = {
    "chatgpt": "ChatGPT", "chat gpt": "ChatGPT", "شات جي بي تي": "ChatGPT", "claude": "Claude",
    "كلود": "Claude", "gemini": "Gemini", "copilot": "Copilot", "deepseek": "DeepSeek",
}


def destination(text: str, lang: str = "en") -> str:
    lowered = text.lower()
    for needle, name in DESTINATIONS.items():
        if needle in lowered:
            return name
    return TEXT[lang]["default_dest"]


def split_question(text: str) -> tuple[str, str]:
    """A first paragraph that ends in a question mark is the question; the rest is the content."""
    first, sep, rest = text.partition("\n\n")
    if sep and rest.strip() and len(first) < 300 and first.strip().endswith(("?", "؟")):
        return first.strip(), rest
    return "", text


def things(entities: list[dict], lang: str = "en") -> str:
    """What was found, in plain words: "a name, an email address and a phone number"."""
    t = TEXT[lang]
    names = list(dict.fromkeys(
        t["things"].get(e["entity_type"], e["entity_type"].lower().replace("_", " "))
        for e in sorted(entities, key=lambda e: e["start"])
    ))
    if len(names) < 2:
        return "".join(names)
    joiner = "، " if lang == "ar" else ", "
    return f"{joiner.join(names[:-1])}{t['and']}{names[-1]}"


def copy_box(text: str, label: str, lang: str = "en") -> str:
    t = TEXT[lang]
    # The button copies the text shown next to it, so nothing else ends up on the clipboard.
    return (
        f'<div class="sitr-ready"><div class="sitr-ready-head"><span>{escape(label)}</span>'
        f'<button type="button" class="sitr-copy" data-done="{t["copied"]}" '
        'onclick="navigator.clipboard.writeText(this.closest(\'.sitr-ready\')'
        ".querySelector('.sitr-quote').innerText); this.textContent = this.dataset.done;\">"
        f'{t["copy"]}</button></div><div class="sitr-quote" dir="auto">{escape(text)}</div></div>'
    )


def reply(result: dict, lang: str = "en", dest: str | None = None, from_file: bool = False) -> str:
    """The answer to "can I send this?": a verdict, why, and the version that is safe to use."""
    t, analysis, key = TEXT[lang], result["analysis"], _decision(result)
    dest = dest or t["default_dest"]
    chip, headline, why = t["answer"][key]
    found = things(analysis["entities"], lang)
    why = why.format(
        things=found, reason=reason(result, lang),
        with_things=f"{t['with_things_prefix']}{found}" if found else "",
    )
    redaction = result["redaction"]
    ready = ""
    if redaction and key != "error":
        content, safe = redaction["original_text"], redaction["safe_text"]
        if key == "allow":
            ready = f'<p class="sitr-note">{t["original_ok"]}</p>' if from_file else copy_box(
                content, t["ready_text"], lang)
        else:
            label = {"redact": t["ready_text"], "private": t["ready_text_limited"],
                     "block": t["ready_secret"]}[key]
            ready = copy_box(safe, label, lang)
    more = ""
    if redaction and analysis["entities"]:
        more = (
            f'<div class="sitr-quote" dir="auto">'
            f"{findings_html(redaction['original_text'], analysis['entities'])}</div>"
        )
    return (
        f'<div class="sitr-reply" dir="{_dir(lang)}"><span class="sitr-chip {key}">'
        f'{escape(chip)}</span><p class="sitr-headline">{escape(headline.format(dest=dest))}</p>'
        f'<p class="sitr-why">{escape(why)}</p>{ready}'
        f'<details class="sitr-more"><summary>{t["see_found"]}</summary>{more}'
        f"{technical_details(result, lang)}</details></div>"
    )


def exports(result: dict, path: str | None, lang: str = "en") -> tuple[list[str], bool]:
    """The redacted file to send back for an upload, and whether a redacted PDF failed.

    A typed message gets no file: its safe version is the text in the reply. A PDF gets a
    redacted PDF, or a redacted text file when the PDF cannot be made safely.
    """
    key, redaction = _decision(result), result["redaction"]
    if not path or key in ("allow", "error") or not redaction or not redaction["replacements"]:
        return [], False
    safe = RedactionResult(**redaction)
    if Path(path).suffix.lower() == ".pdf":
        pdf = redacted_pdf(path, safe)
        if pdf:
            return [str(pdf)], False
        return [str(redacted_text_file(safe))], True
    return [str(redacted_text_file(safe))], False


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
    risk = t["not_assessed"] if _decision(result) == "error" else (
        f"{t['risk_levels'][analysis['risk_level']]}{'، ' if lang == 'ar' else ', '}"
        + t["of_100"].format(score=analysis["risk_score"])
    )
    return (
        f'<div class="sitr-tech"><h4>{t["details_label"]}</h4>'
        f"<p>{t['risk']}: {escape(risk)}<br>"
        f"{t['reason_codes']}: {escape(', '.join(analysis['reason_codes']) or t['none'])}<br>"
        f"{t['detector_used']}: {escape(metadata['detector'])}<br>"
        f"{t['classifier_used']}: {escape(metadata['classifier'])}<br>"
        f"{t['time']}: {result['latency_ms']} ms</p>{table}</div>"
    )


def user_bubble(item: dict, lang: str = "en") -> str:
    text = f'<span dir="auto">{escape(item["text"])}</span>' if item["text"] else ""
    attached = (
        f'<span class="meta" dir="{_dir(lang)}">{TEXT[lang]["attached"]}: '
        f'{escape(item["filename"])}</span>' if item["filename"] else ""
    )
    return f'<div class="sitr-user">{text}{attached}</div>'


def messages(items: list[dict], lang: str = "en") -> list[dict]:
    """The whole conversation, rebuilt from what was sent and decided."""
    chat = []
    for item in items:
        chat.append({"role": "user", "content": user_bubble(item, lang)})
        content = (
            f'<div class="sitr-pending">{TEXT[lang]["pending"]}</div>'
            if item["result"] is None else reply(
                item["result"], lang, destination(item["text"], lang), bool(item["filename"])
            )
        )
        chat.append({"role": "assistant", "content": content})
        if item.get("files") or item.get("pdf_failed"):
            note = TEXT[lang]["pdf_not_safe"] if item.get("pdf_failed") else ""
            chat.append({"role": "assistant", "content": (
                f'<div class="sitr-files" dir="{_dir(lang)}">{TEXT[lang]["files_ready"]}'
                f"{f'<p>{note}</p>' if note else ''}</div>"
            )})
            chat += [{"role": "assistant", "content": {"path": f}} for f in item["files"]]
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
    tiles = f'<div class="sitr-kpi" style="--kpi:var(--sitr-muted)"><b>{total}</b>' \
        f'<span>{t["kpi_inspected"]}</span></div>'
    tiles += "".join(
        f'<div class="sitr-kpi" style="--kpi:var(--sitr-{a})"><b>{stats[a]}</b>'
        f"<span>{names[a]}</span></div>"
        for a in ACTION_ORDER
    )
    bar = "".join(
        f'<span style="width:{stats[a] / total * 100:.2f}%;background:var(--sitr-{a})" '
        f'title="{names[a]}: {stats[a]}"></span>'
        for a in ACTION_ORDER if stats[a]
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
        f'<div dir="{_dir(lang)}"><div class="sitr-kpis">{tiles}</div>'
        f'<div class="sitr-bar" role="img" aria-label="{t["tab_dashboard"]}">{bar}</div>'
        f"<h4>{t['found_label']}</h4>{table}</div>"
    )


def readiness(lang: str = "en") -> str:
    """Whether each model is ready, for the header."""
    t = TEXT[lang]
    parts = []
    for name, module in ((t["detector"], hf_detection), (t["classifier"], risk_classifier)):
        state = module.status()["state"]
        css = "ready" if state == "ready" else "down" if state == "unavailable" else ""
        parts.append(f'<span class="{css}">{name} {t["states"].get(state, state)}</span>')
    return f'<div class="sitr-models">{"".join(parts)}</div>'


def brand(lang: str = "en") -> str:
    t = TEXT[lang]
    return (
        f'<div class="sitr-brand" dir="{_dir(lang)}"><span class="ar" lang="ar">سِتر</span>'
        f'<span class="en">{t["product"]}</span><span class="tag">{t["tagline"]}</span></div>'
    )


def status(lang: str = "en") -> str:
    """Model readiness for the sidebar."""
    return (
        f'<div class="sitr-status" dir="{_dir(lang)}"><h4>{TEXT[lang]["models_title"]}</h4>'
        f"{readiness(lang)}</div>"
    )


def page_title(page: str, lang: str = "en") -> str:
    key = {"dashboard": "tab_dashboard", "how": "tab_how"}[page]
    return f'<h2 class="sitr-page-title" dir="{_dir(lang)}">{TEXT[lang][key]}</h2>'


def show_page(page: str, lang: str = "en") -> tuple:
    """Show one page and mark its sidebar entry."""
    return (
        page,
        *(gr.Column(visible=page == p) for p in PAGES),
        *(gr.Button(variant="primary" if page == p else "secondary") for p in PAGES),
        dashboard(lang),
    )


def empty_chat(lang: str = "en") -> str:
    t = TEXT[lang]
    return (
        f'<div class="sitr-empty" dir="{_dir(lang)}"><div class="ar" lang="ar">سِتر</div>'
        f"<h3>{t['empty_title']}</h3><p>{t['empty_hint']}</p></div>"
    )


def chat_examples(lang: str = "en") -> list[dict]:
    return [
        {"text": f"{label}\n\n{text}", "display_text": label}
        for label, text in zip(TEXT[lang]["examples"], EXAMPLES.values(), strict=True)
    ]


def send(message: dict | None, items: list[dict], lang: str = "en"):
    """Show the question at once, then Sitr's answer when the check finishes."""
    message = message or {}
    text = (message.get("text") or "").strip()
    files = message.get("files") or []
    path = files[0] if files else None
    if isinstance(path, dict):
        path = path.get("path")
    if not text and not path:
        yield messages(items, lang), gr.MultimodalTextbox(), items, dashboard(lang)
        return
    # A question typed above the content is not part of what the user would send, and checking
    # it with the content misleads the model ("Claude" read as a name, a real name missed), so
    # only the content is checked.
    content = split_question(text)[1] if not path else None
    item = {"text": text, "filename": Path(path).name if path else None, "result": None}
    pending = [*items, item]
    yield messages(pending, lang), gr.MultimodalTextbox(value=None, interactive=False), items, \
        dashboard(lang)
    # With a file, the typed text is the question and the file is what gets checked. No model is
    # called: Sitr answers, and the user takes the safe version to their own assistant. Uploads
    # are Gradio temp copies, kept until their redacted copy is made, then deleted.
    try:
        item["result"] = inspect_and_process(text=content, file_path=path, route_to_model=False)
        item["files"], item["pdf_failed"] = exports(item["result"], path, lang)
    finally:
        if path:
            Path(path).unlink(missing_ok=True)
    record(item["result"])
    yield messages(pending, lang), gr.MultimodalTextbox(value=None, interactive=True), pending, \
        dashboard(lang)


def send_example(evt: gr.SelectData, items: list[dict], lang: str = "en"):
    yield from send({"text": evt.value["text"]}, items, lang)


def switch_language(lang: str, items: list[dict]) -> tuple:
    """Show every label, and the whole conversation, in the other language."""
    new = "ar" if lang == "en" else "en"
    t = TEXT[new]
    return (
        new,
        gr.Button(value=t["switch"]),
        brand(new),
        status(new),
        gr.Button(value=f"+  {t['new_chat']}"),
        gr.Button(value=t["tab_inspect"]),
        gr.Button(value=t["tab_dashboard"]),
        gr.Button(value=t["tab_how"]),
        gr.Chatbot(value=messages(items, new), placeholder=empty_chat(new),
                   examples=chat_examples(new), rtl=new == "ar"),
        gr.MultimodalTextbox(placeholder=t["placeholder"], rtl=new == "ar"),
        page_title("dashboard", new),
        t["dashboard_intro"],
        dashboard(new),
        gr.Button(value=t["refresh"]),
        page_title("how", new),
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
    page_state = gr.State("chat")
    conversation = gr.State([])
    with gr.Sidebar(elem_id="sitr-sidebar", width=268, open=True):
        brand_output = gr.HTML(brand())
        new_chat_button = gr.Button(f"+  {EN['new_chat']}", variant="secondary", elem_id="sitr-new")
        with gr.Column(elem_classes="sitr-nav"):
            nav_buttons = [
                gr.Button(EN["tab_inspect"], variant="primary"),
                gr.Button(EN["tab_dashboard"], variant="secondary"),
                gr.Button(EN["tab_how"], variant="secondary"),
            ]
        with gr.Column(elem_id="sitr-foot"):
            status_output = gr.HTML(status())
            with gr.Row(elem_id="sitr-toggles"):
                lang_button = gr.Button(EN["switch"], size="sm", variant="secondary")
                theme_button = gr.Button(
                    "☾", size="sm", variant="secondary", elem_id="sitr-theme"
                )
    with gr.Column(elem_id="sitr-main"):
        with gr.Column(visible=True) as chat_page:
            chat = gr.Chatbot(
                elem_id="sitr-chat", show_label=False, height="calc(100dvh - 190px)",
                min_height=360, placeholder=empty_chat(), examples=chat_examples(),
                sanitize_html=False, render_markdown=False, layout="bubble", autoscroll=True,
                buttons=["copy"],
            )
            composer = gr.MultimodalTextbox(
                placeholder=EN["placeholder"], show_label=False, file_count="single",
                file_types=[".pdf", ".txt", ".md", ".csv", ".py", ".js", ".ts", ".java",
                            ".json", ".yml", ".yaml", ".env", ".sql", ".sh"],
                sources=["upload"], elem_id="sitr-composer", autofocus=True,
            )
        with gr.Column(visible=False) as dashboard_page:
            dashboard_title = gr.HTML(page_title("dashboard"))
            dashboard_intro = gr.Markdown(EN["dashboard_intro"])
            dashboard_output = gr.HTML(dashboard())
            refresh_button = gr.Button(EN["refresh"], size="sm", variant="secondary")
            refresh_button.click(dashboard, lang_state, dashboard_output)
        with gr.Column(visible=False) as how_page:
            how_title = gr.HTML(page_title("how"))
            how_output = gr.Markdown(EN["how"])

    pages = [chat_page, dashboard_page, how_page]
    for page, button in zip(PAGES, nav_buttons, strict=True):
        button.click(
            lambda lang, page=page: show_page(page, lang), lang_state,
            [page_state, *pages, *nav_buttons, dashboard_output],
        ).then(None, js=CLOSE_SIDEBAR_ON_PHONE_JS)
    outputs = [chat, composer, conversation, dashboard_output]
    composer.submit(send, [composer, conversation, lang_state], outputs)
    chat.example_select(send_example, [conversation, lang_state], outputs)
    # The trash icon and "New chat" both start a new conversation.
    chat.clear(lambda: [], None, conversation)
    new_chat_button.click(
        lambda lang: ([], [], *show_page("chat", lang)), lang_state,
        [chat, conversation, page_state, *pages, *nav_buttons, dashboard_output],
    ).then(None, js=CLOSE_SIDEBAR_ON_PHONE_JS)
    lang_button.click(
        switch_language, [lang_state, conversation],
        [lang_state, lang_button, brand_output, status_output, new_chat_button, *nav_buttons,
         chat, composer, dashboard_title, dashboard_intro, dashboard_output,
         refresh_button, how_title, how_output],
    ).then(None, lang_button, js=SET_DIRECTION_JS)
    theme_button.click(None, None, theme_button, js=THEME_TOGGLE_JS)
    demo.load(None, None, theme_button, js=THEME_LOAD_JS).then(
        None, js=CLOSE_SIDEBAR_ON_PHONE_JS
    )
    gr.Timer(5).tick(status, lang_state, status_output)
    demo.load(status, lang_state, status_output)

if __name__ == "__main__":
    enable_audit_log()
    warm_up()
    demo.launch(theme=THEME, css=CSS, head=HEAD, footer_links=[])
