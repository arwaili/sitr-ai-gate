# Sitr Task Board

**Read this first.** It is the live status of the project: who owns what, what is done, what is next, and what is blocked. Every person and agent updates it as they work (see the rules in `CLAUDE.md`).

- **Deadline:** Saturday, November 7, 2026, 2:00 PM Qatar time. Internal deadline: **12:30 PM**.
- **Repository:** https://github.com/arwaili/sitr-ai-gate
- **Dataset:** https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp
- **Space:** not deployed yet

## Current status

Updated 2026-11-06 after PR #9.

| Phase | State |
|---|---|
| 1 - Setup | Done (S1-S8; S8 team HF org skipped by decision) |
| 2 - Mock pipeline and dataset | Done, merged in PRs #1-#5 |
| 3 - Ingestion and deterministic security | Done, merged in PR #8 |
| 4 - Hugging Face intelligence | Built on `feature/hf-intelligence`, in review (H1-H4) |
| 5 - Policy, routing, integration | Not started (P1-P5); P1 needs Phase 3 (done) and Phase 4 |
| 6-7 - Product and deployment | Not started (U1-U4); UI work can start now, deploy after P1 |
| 8-9 - Review and submission | Not started (R1-R3) |

What works on `main` now: 117 tests pass plus T7 (expected failure until P1). The real Phase 3 modules (`ingest`, `detect_deterministic`) work and are tested, but the app does not call them yet: the orchestrator still uses its own mock patterns and a text-only file reader, so the four pasted demo texts work in the app while uploaded PDFs return a safe error until P1. Phase 4 (`detect_entities`, `classify_risk` with the real models) is on `feature/hf-intelligence`, waiting for review.

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
| I5 | Placeholder keys in documentation (`sk-XXXX`) are not reported. T7 in `test_policy.py` stays xfail until P1 makes the orchestrator call `detect_deterministic` | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I6 | Demo files in `examples/`: `synthetic_cv.pdf`, `synthetic_contract.pdf` (2 pages), `vulnerable_code.py`, `safe_prompt.txt`; rebuild PDFs with `examples/make_examples.py` (needs Chrome) | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |
| I7 | Demo phone numbers use `+974 0000 01xx` (not assigned to subscribers) in `examples/` and `app.py`. The published dataset and `test_policy.py` still use `+974 5555 01xx`, see H4 | Saad | Abdulaziz | done | [#8](https://github.com/arwaili/sitr-ai-gate/pull/8) |

## Phase 4 - Hugging Face intelligence (Mohammed)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| H1 | `OpenMed/privacy-filter-multilingual-v2` loads lazily on CPU (bfloat16), cached, 30 s timeout, rules-only fallback; 18 OpenMed labels mapped to Sitr types; split words grown to whole words; threshold tuned on dev | Mohammed | Abdulaziz | in review | |
| H2 | `Horizon-Labs/multilingual-zeroshot-small` scores one English description per risk level (works for Arabic); keyword fallback on failure or timeout | Mohammed | Abdulaziz | in review | |
| H3 | `data/evaluate.py` runs locally on CPU (no GPU needed); results in `data/eval_results_test.json` and `README.md` | Mohammed | Abdulaziz | in review | |
| H4 | Dataset card rewritten (filter checks, phone range); Qwen sentences scanned with OpenMed (no real names); phones moved to `+974 0000` locally. Republishing to the Hub is part of this PR's push | Mohammed | Abdulaziz | in review | |

## Phase 5 - Policy, routing and integration (Rashid)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| P1 | Checkpoint C: orchestrator calls `ingest`, `detect_deterministic`, `detect_entities` and `classify_risk` instead of its mock detection | Rashid | | open | |
| P2 | Merge and deduplicate findings from rules and models; rules stay authoritative | Rashid | | open | |
| P3 | Full policy overrides from `PROJECT_OVERVIEW.md` Phase 5 | Rashid | | open | |
| P4 | Real `call_model` with Qwen through Hugging Face Inference Providers, with a timeout and a safe fallback | Rashid | | open | |
| P5 | Remove uploaded temp files on success and failure | Rashid | | open | |

## Phase 6 and 7 - Product and deployment (Abdulaziz)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| U1 | Dashboard: requests inspected, redacted, private, blocked; entity categories | Abdulaziz | | open | |
| U2 | Arabic RTL rendering, intended-task input, entity counts, route used, collapsible technical details | Abdulaziz | | open | |
| U3 | Deploy the Hugging Face Space: Space metadata in README, slim Space requirements, secrets in Space settings | Abdulaziz | | open | |
| U4 | Test the Space from a clean browser and another device; measure cold and warm latency | anyone | | open | |

## Phase 8 and 9 - Security review and submission (everyone)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| R1 | Adversarial review of another person's lane (bypasses, leaks, failures); add regression tests | everyone | | open | |
| R2 | 90-second demo script, 3-minute pitch, submission description | Abdulaziz | | open | |
| R3 | Backup screenshots and video | anyone | | open | |

## Blockers

- `main` is not protected: the repository is private on a free plan. Follow the PR rules anyway.
- GitHub usernames are not yet matched to people, so `CODEOWNERS` is not filled in.
- Until P1, the app's orchestrator uses mock detection and does not call the Phase 3 rules or the Phase 4 models, and it cannot read PDFs. Use `src.ingestion.ingest` and `src.deterministic.detect_deterministic` directly to test Phase 3.

## Log

Newest first. One line per finished piece of work: date and time (Qatar), name, what changed, PR.

- 2026-11-06 - Abdulaziz - Phase 4 (H1-H4) built on `feature/hf-intelligence`. Held-out test split (60 rows), rules plus models: entity precision 0.967, recall 0.927; names 0.897/0.897; action accuracy 0.95 (all misses are public prompts with a false Arabic name); risk model alone 0.85. Median latency: PII model 234 ms, risk model 146 ms. 132 tests pass locally; CI skips the 7 real-model tests.
- 2026-11-06 - Abdulaziz - PR #8 merged into `main` (117 tests pass after merge), I1-I7 marked done in [#9](https://github.com/arwaili/sitr-ai-gate/pull/9), lane branches synced to `main`, docs brought up to date.
- 2026-11-06 - Abdulaziz - Phase 3 (I1-I7) built on `feature/ingestion`: real PDF ingestion, 27 deterministic patterns, demo files. 117 tests pass plus T7 (xfail until P1). On the 240-row dev split, structured entities (names excluded) score precision 1.000, recall 0.962; the four demo files give allow, redact, private, block through the policy engine. Worst-case inputs run in about 1 s per 2 MB. [#8](https://github.com/arwaili/sitr-ai-gate/pull/8)
- 2026-11-06 - Abdulaziz - PRs #1, #2, #5, #3, #4 merged in order. Merged `main`: 62 tests pass plus 1 expected failure (T7); Ruff, compile, offline four-scenario check (allow, redact, private, block) and secret scan all pass; contracts unchanged since `887963c`. Clean-venv install confirmed (S7). Collaborators invited (S6). Team HF org skipped (S8): dataset, jobs and the Space stay on `arwaili`.
- 2026-11-06 - Abdulaziz - Task board and team workflow added to `TASKS.md` and `CLAUDE.md`. [#1](https://github.com/arwaili/sitr-ai-gate/pull/1)
- 2026-11-06 - Abdulaziz - Dataset `arwaili/sitr-synthetic-dlp` generated with Qwen in an HF Job and published (300 examples). [#5](https://github.com/arwaili/sitr-ai-gate/pull/5)
- 2026-11-05 - Abdulaziz - Contracts locked at `887963c`; mocks for all four lanes and the Gradio shell built. PRs [#1](https://github.com/arwaili/sitr-ai-gate/pull/1) to [#5](https://github.com/arwaili/sitr-ai-gate/pull/5)
