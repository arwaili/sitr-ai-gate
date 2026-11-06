# Sitr Task Board

**Read this first.** It is the live status of the project: who owns what, what is done, what is next, and what is blocked. Every person and agent updates it as they work (see the rules in `CLAUDE.md`).

- **Deadline:** Saturday, November 7, 2026, 2:00 PM Qatar time. Internal deadline: **12:30 PM**.
- **Repository:** https://github.com/arwaili/sitr-ai-gate
- **Dataset:** https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp
- **Space:** https://huggingface.co/spaces/arwaili/sitr-ai-gate (public)

## Current status

Updated 2026-11-06 after PR #23.

| Phase | State |
|---|---|
| 1 - Setup | Done (S1-S8; S8 team HF org skipped by decision) |
| 2 - Mock pipeline and dataset | Done, merged in PRs #1-#5 |
| 3 - Ingestion and deterministic security | Done, merged in PR #8 |
| 4 - Hugging Face intelligence | Done, merged in PR #11; dataset republished on the Hub |
| 5 - Policy, routing, integration | Done, merged in PR #14 |
| 6-7 - Product and deployment | Done: U1-U3 merged in PRs #21 and #23 (customer chat UI, English/Arabic switch); the Space is live and public and runs `main`; U4 measured and checked on a phone |
| 8-9 - Review and submission | R1 in progress (Saad); R2-R3 not started |

What works on `main` now, and on the public Space (https://huggingface.co/spaces/arwaili/sitr-ai-gate): Phases 1-7. The app is a chat: type a message and press Enter, or press + to attach a PDF, code or text file. Each reply shows, in order, Sitr's decision, what it found, exactly what the AI model received (placeholders only on redact, nothing on block), and the answer. A header button switches the whole app between English and Arabic (right-to-left). Allow and redact are answered by hosted Qwen, private by Qwen inside the app, and block reaches no model. Uploads are deleted after inspection. If the PII detector is down, messages are blocked. 212 tests pass locally (CI: 200, with 12 model tests skipped). Measured results are in `README.md`.

## Team

| Person | Default lane | Branch | Owns |
|---|---|---|---|
| Abdulaziz | 4 - Product, deployment, coordination | `feature/product` | `app.py`, `requirements.txt`, `README.md`, `assets/`, `tests/test_end_to_end.py`, the Space, the pitch |
| Saad | 1 - Ingestion and deterministic security | `feature/ingestion` | `src/ingestion.py`, `src/deterministic.py`, `examples/`, `tests/test_ingestion.py` |
| Mohammed | 2 - Hugging Face intelligence | `feature/hf-intelligence` | `src/hf_detection.py`, `src/risk_classifier.py`, `data/`, `tests/test_detection.py` |
| Rashid | 3 - Policy, routing and orchestration | `feature/policy-routing` | `src/policy_engine.py`, `src/redactor.py`, `src/router.py`, `src/audit.py`, `src/orchestrator.py`, `tests/test_policy.py` |

Lanes are defaults, not walls. **Anyone may take any open task, including one in another lane.** Claim it in the table below before starting, and ask the lane owner to review the PR when it touches their files.

## How to claim a task

1. Pull `main`. Check that the task's **Status** is `open` and nobody is in **Claimed by**.
2. Set **Claimed by** to your name and **Status** to `in progress`. Push that one-line change on your branch, or tell the team in the group chat if you cannot push yet.
3. Work on the task's branch, or on `task/<short-name>` for work outside your lane.
4. When it is done, set **Status** to `in review`, link the PR, and add a line to the **Log**.
5. After the merge, set **Status** to `done`.

If a task has been `in progress` with no commits for 3 hours, ask its claimer before taking it over.

Status values: `open`, `in progress`, `in review`, `blocked`, `done`.

## Phase 1 and 2 - Setup and mock pipeline

Mocks for every lane, the mock pipeline with all four decisions, the Gradio shell, and the synthetic dataset are built. **Done.** All five PRs were merged into `main` on 2026-11-06 in this order, with the full test suite run after each merge.

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| S1 | Merge setup: overview, contract notes, task board, full CI | Abdulaziz | | done | [#1](https://github.com/arwaili/sitr-ai-gate/pull/1) |
| S2 | Merge Lane 1 mocks | Saad | | done | [#2](https://github.com/arwaili/sitr-ai-gate/pull/2) |
| S3 | Merge Lane 2 mocks and the dataset generator | Mohammed | | done | [#5](https://github.com/arwaili/sitr-ai-gate/pull/5) |
| S4 | Merge Lane 3 orchestrator, policy, redaction, routing, audit | Rashid | | done | [#3](https://github.com/arwaili/sitr-ai-gate/pull/3) |
| S5 | Merge Lane 4 Gradio shell (it contains S4, so merge it last) | Abdulaziz | | done | [#4](https://github.com/arwaili/sitr-ai-gate/pull/4) |
| S6 | Add all four people as GitHub collaborators (invited: `malaliQA`, `astro0707-c`, `ralkubai`; each must accept the invite) | Abdulaziz | | done | |
| S7 | Confirm `pip install -r requirements.txt` works in a clean Python 3.11 venv (passes: torch 2.15, transformers 5.22, gradio 6.31 import; PyMuPDF warns that `fitz` is deprecated, use `import pymupdf`) | anyone | Abdulaziz | done | |
| S8 | Team Hugging Face org and credits: skipped by decision; everything stays on `arwaili` | Abdulaziz | | done | |

## Phase 3 - Ingestion and deterministic security (Saad)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| I1 | Digital PDF extraction with PyMuPDF, page mapping, Arabic preserved (RTL lines rebuilt in reading order, presentation forms folded) | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I2 | Empty, corrupted, encrypted, oversized (10 MB), too-long (50 pages), image and unsupported files fail with content-free messages. Ingestion creates no temp files; deleting uploads is P5 | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I3 | Detectors: Qatar phone, synthetic QID, passport-like ID, IBAN, account numbers, salaries and amounts (Arabic and English) | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I4 | Secret detectors: API keys (sk-, hf_, gh*_, xox*-, assigned keys), bearer tokens, JWTs, passwords (quoted, unquoted, prose), database URLs, private-key blocks, cloud keys (high: internal IPs and hosts) | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I5 | Placeholder keys in documentation (`sk-XXXX`) are not reported. T7 in `test_policy.py` passes since P1 (#14) | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I6 | Demo files in `examples/`: `synthetic_cv.pdf`, `synthetic_contract.pdf` (2 pages), `vulnerable_code.py`, `safe_prompt.txt`; rebuild PDFs with `examples/make_examples.py` (needs Chrome) | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I7 | Demo phone numbers use `+974 0000 01xx` (not assigned to subscribers) in `examples/` and `app.py`. The published dataset moved to `+974 0000` in H4; only `tests/test_policy.py` still uses `+974 5555 01xx` | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |

## Phase 4 - Hugging Face intelligence (Mohammed)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| H1 | `OpenMed/privacy-filter-multilingual-v2` loads lazily on CPU (bfloat16), cached, 30 s timeout, rules-only fallback; 18 OpenMed labels mapped to Sitr types; split words grown to whole words; threshold tuned on dev | Mohammed | Abdulaziz | done | [#11](https://github.com/arwaili/sitr-ai-gate/pull/11) |
| H2 | `Horizon-Labs/multilingual-zeroshot-small` scores one English description per risk level (works for Arabic); keyword fallback on failure or timeout | Mohammed | Abdulaziz | done | [#11](https://github.com/arwaili/sitr-ai-gate/pull/11) |
| H3 | `data/evaluate.py` runs locally on CPU (no GPU needed); results in `data/eval_results_test.json` and `README.md` | Mohammed | Abdulaziz | done | [#11](https://github.com/arwaili/sitr-ai-gate/pull/11) |
| H4 | Dataset card rewritten (filter checks, phone range); Qwen sentences scanned with OpenMed (no real names); phones moved to `+974 0000` locally. Republished to the Hub (commit `97553b09`) | Mohammed | Abdulaziz | done | [#11](https://github.com/arwaili/sitr-ai-gate/pull/11) |

## Phase 5 - Policy, routing and integration (Rashid)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| P1 | Orchestrator calls `ingest`, `detect_deterministic`, `detect_entities` and `classify_risk`; models are skipped when a rule finds a credential; metadata says which models ran or fell back; app warms all models at start | Rashid | Abdulaziz | done | [#14](https://github.com/arwaili/sitr-ai-gate/pull/14) |
| P2 | `policy_engine.merge_findings`: rules first, overlapping model findings dropped; T7 passes | Rashid | Abdulaziz | done | [#14](https://github.com/arwaili/sitr-ai-gate/pull/14) |
| P3 | All Phase 5 overrides: credentials, private keys and restricted operational information block; HR/financial data, a model-only credential or the classifier (confidence 0.6 or more) route private; models can never block or lower a decision | Rashid | Abdulaziz | done | [#14](https://github.com/arwaili/sitr-ai-gate/pull/14) |
| P4 | Hosted Qwen via HF Inference Providers (`featherless-ai`) for allow and redact; local Qwen inside Sitr for private, so originals never leave; timeouts and a notice on failure | Rashid | Abdulaziz | done | [#14](https://github.com/arwaili/sitr-ai-gate/pull/14) |
| P5 | `inspect_and_process(..., delete_file=True)` removes the upload on success and failure; the app uses it | Rashid | Abdulaziz | done | [#14](https://github.com/arwaili/sitr-ai-gate/pull/14) |

## Phase 6 and 7 - Product and deployment (Abdulaziz)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| U1 | Dashboard tab: inspected, allowed, redacted, private, blocked and error counts plus entity categories; in memory, metadata only, shared by all visitors | Abdulaziz | Abdulaziz | done | [#21](https://github.com/arwaili/sitr-ai-gate/pull/21) |
| U2 | Customer chat UI: one scrolling column, ChatGPT-style composer (Enter sends, + attaches a file), replies in a fixed order (decision seal, findings highlighted, what the model received, answer, technical details), suggestion cards, pending message, new-chat button; English/Arabic switch with a right-to-left page; fixed task list so no free text reaches a model; header keeps one size on every tab | Abdulaziz | Abdulaziz | done | [#21](https://github.com/arwaili/sitr-ai-gate/pull/21), [#23](https://github.com/arwaili/sitr-ai-gate/pull/23) |
| U3 | `space/`: Space README with metadata, CPU-only requirements (torch wheel 210 MB, resolution checked for Linux), `deploy_space.py`; the app warms all models at start. Deployed on cpu-basic, now public; `HF_TOKEN` secret set; models load at start | Abdulaziz | Abdulaziz | done | [#21](https://github.com/arwaili/sitr-ai-gate/pull/21) |
| U4 | Live Space over its API: 11 requests (examples, repeats, three uploads) give the right badge with no leaked value. Time per request: block 1.5-2 s, redact 5-8 s, allow 4-23 s (hosted provider), private 18-33 s (local Qwen on 2 vCPU). The chat UI was rechecked on the live Space; Abdulaziz confirmed it works on a phone | anyone | Abdulaziz | done | [#21](https://github.com/arwaili/sitr-ai-gate/pull/21) |

## Phase 8 and 9 - Security review and submission (everyone)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| R1 | Adversarial review of another person's lane (bypasses, leaks, failures); add regression tests | everyone | Saad | in progress | |
| R2 | 90-second demo script, 3-minute pitch, submission description | Abdulaziz | | open | |
| R3 | Backup screenshots and video | anyone | | open | |

## Blockers

- `main` is not protected: the repository is private on a free plan. Follow the PR rules anyway.
- GitHub usernames are not yet matched to people, so `CODEOWNERS` is not filled in.
- Requests are blocked until the PII model has loaded, so open the Space and run one inspection before any demo.
- The Space has its `HF_TOKEN` secret and runs on CPU Basic (16 GB RAM; the three models use about 6.5 GB). Redeploy with `python space/deploy_space.py --public` after each merge that changes `app.py`, `ui_text.py`, `src/` or `examples/`.
- Open PRs to update against `main`: [#18](https://github.com/arwaili/sitr-ai-gate/pull/18) conflicts in `app.py` (keep `main`'s version, which already has its audit-log, cache-purge and file-clearing fixes); [#20](https://github.com/arwaili/sitr-ai-gate/pull/20) duplicates the merged Space package (`space/`), so only its `.env.example` and `requirements-dev.txt` parts are still needed; [#19](https://github.com/arwaili/sitr-ai-gate/pull/19) is waiting for Rashid's review.

## Log

Newest first. One line per finished piece of work: date and time (Qatar), name, what changed, PR.

- 2026-11-06 - Abdulaziz - On `task/u2-app-shell`: sidebar app shell (New chat, Chat / Dashboard / How it works, model status, language and light/dark toggles; the theme is remembered), full-page chat, dashboard tiles. Each reply now says what to do next: "Safe to send" with the text, "Send this version instead" with the redacted text, or "Don't send this" with a safer version. A Copy button copies exactly that text, and a redacted .txt, plus a redacted PDF for PDF uploads, is offered as a download. The redacted PDF is read back and refused if any found value remains (`src/export.py`). 219 tests pass (CI: 207).
- 2026-11-06 - Abdulaziz - PR #23 merged into `main` (212 tests pass after merge, CI green) and deployed: all 19 Space files match `main`. Live check on the public Space: the CV suggestion was redacted and the model received placeholders only. U4 done (phone confirmed). Lane branches synced. [#23](https://github.com/arwaili/sitr-ai-gate/pull/23)
- 2026-11-06 - Abdulaziz - Customer version of the UI on `task/u2-redesign`: the Inspect tab is now a chat (one column, scrolls like a phone conversation). A ChatGPT-style composer sends on Enter and attaches a file with +. Each reply runs in order: Sitr's decision, what Sitr found (highlighted), exactly what the AI model received, the answer, then collapsed technical details. Suggestion cards when the chat is empty; a pending message while Sitr checks; the trash icon starts a new chat; the header keeps one size on every tab; Gradio's footer is hidden. 212 tests pass (CI: 200). Checked in both languages, light and dark, desktop and phone.
- 2026-11-06 - Abdulaziz - U2 redesign on `task/u2-redesign`: an English/العربية switch shows one language at a time (the page turns right-to-left in Arabic, and every label, reason, risk, route, dashboard line and the How it works tab are translated); the decision is a large colored seal; one-click examples; grouped input and result panels; Qatar maroon theme with Readex Pro and Reem Kufi; on a phone the decision scrolls into view; blocked inputs show that nothing was sent. 210 tests pass (CI: 198, 12 model tests skip). Checked in the browser in both languages, light and dark, desktop and phone.
- 2026-11-06 - Abdulaziz - PR #21 merged into `main` (201 tests pass after merge, CI green), U1-U3 marked done, lane branches synced.
- 2026-11-06 - Abdulaziz - Space made public; it loads without signing in.
- 2026-11-06 - Abdulaziz - Space deployed after `arwaili` moved to PRO: https://huggingface.co/spaces/arwaili/sitr-ai-gate (private). First build failed because the Space installs `gradio[oauth,mcp]`, which pins pydantic to 2.12.x; the pin was loosened (tests pass on 2.12.5). U4 over the API: all 11 requests correct, no leaks; timings in U4.
- 2026-11-06 - Abdulaziz - U1-U3 built on `feature/product`: dashboard, task field, RTL, details panel, Space package. Also includes PR #18's app fixes (audit log, purge of uninspected uploads, file box cleared). 201 tests pass (CI: 189, 12 model tests skip). Live check in the browser: four examples, three uploads and a translate task give the right badge, no value leaks, dashboard counts match. [#21](https://github.com/arwaili/sitr-ai-gate/pull/21). Space deploy tried and refused (needs HF PRO); nothing was created.
- 2026-11-06 - Saad - R1 findings fixed: secrets written as login phrases (English and Arabic), spaced out, broken up with zero-width characters, or base64-encoded were allowed or sent to the private route. They now block. Dataset (240 rows): no new false blocks, all 60 block rows still caught. Private route checked on a Mac: about 4 s per answer after 17 s to load.
- 2026-11-06 - Saad - R1 finding fixed: when the PII detector timed out or failed, requests continued on rules only, so a name-only prompt showed ALLOWED and would go to hosted Qwen unredacted. Requests now block (`PROCESSING_ERROR`) and nothing reaches a model; the detector status also returns to ready after a failure. 166 tests pass locally. Reproduce on old code with `SITR_MODEL_TIMEOUT=0.01 python app.py`.
- 2026-11-06 - Abdulaziz - PR #14 merged into `main` (160 tests pass after merge, CI green), P1-P5 marked done, lane branches synced, docs updated to match.
- 2026-11-06 - Abdulaziz - Phase 5 (P1-P5) built on `feature/policy-routing`: real pipeline end to end. 160 tests pass (CI: 148 pass, 12 model tests skip); T7 passes. Test split through the full pipeline: action accuracy 0.95, entities 0.968 / 0.938. Live check: four examples and two PDF uploads in the running app give the right badge, uploads are deleted, the audit log holds no values. [#14](https://github.com/arwaili/sitr-ai-gate/pull/14)
- 2026-11-06 - Abdulaziz - Added Phase 4 testing steps to Blockers; deleted the merged `chore/phase-1-setup` branch.
- 2026-11-06 - Abdulaziz - PR #11 merged into `main` (132 tests pass after merge, CI green), H1-H4 marked done, lane branches synced to `main`, docs updated to match.
- 2026-11-06 - Abdulaziz - Phase 4 (H1-H4) built on `feature/hf-intelligence`. Held-out test split (60 rows), rules plus models: entity precision 0.967, recall 0.927; names 0.897/0.897; action accuracy 0.95 (all misses are public prompts with a false Arabic name); risk model alone 0.85. Median latency: PII model 234 ms, risk model 146 ms. 132 tests pass locally; CI skips the 7 real-model tests. Dataset republished with `+974 0000` phones. [#11](https://github.com/arwaili/sitr-ai-gate/pull/11)
- 2026-11-06 - Abdulaziz - PR #8 merged into `main` (117 tests pass after merge), I1-I7 marked done in [#9](https://github.com/arwaili/sitr-ai-gate/pull/9), lane branches synced to `main`, docs brought up to date.
- 2026-11-06 - Abdulaziz - Phase 3 (I1-I7) built on `feature/ingestion`: real PDF ingestion, 27 deterministic patterns, demo files. 117 tests pass plus T7 (xfail until P1). On the 240-row dev split, structured entities (names excluded) score precision 1.000, recall 0.962; the four demo files give allow, redact, private, block through the policy engine. Worst-case inputs run in about 1 s per 2 MB. [#8](https://github.com/arwaili/sitr-ai-gate/pull/8)
- 2026-11-06 - Abdulaziz - PRs #1, #2, #5, #3, #4 merged in order. Merged `main`: 62 tests pass plus 1 expected failure (T7); Ruff, compile, offline four-scenario check (allow, redact, private, block) and secret scan all pass; contracts unchanged since `887963c`. Clean-venv install confirmed (S7). Collaborators invited (S6). Team HF org skipped (S8): dataset, jobs and the Space stay on `arwaili`.
- 2026-11-06 - Abdulaziz - Task board and team workflow added to `TASKS.md` and `CLAUDE.md`. [#1](https://github.com/arwaili/sitr-ai-gate/pull/1)
- 2026-11-06 - Abdulaziz - Dataset `arwaili/sitr-synthetic-dlp` generated with Qwen in an HF Job and published (300 examples). [#5](https://github.com/arwaili/sitr-ai-gate/pull/5)
- 2026-11-05 - Abdulaziz - Contracts locked at `887963c`; mocks for all four lanes and the Gradio shell built. PRs [#1](https://github.com/arwaili/sitr-ai-gate/pull/1) to [#5](https://github.com/arwaili/sitr-ai-gate/pull/5)
