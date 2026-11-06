# Sitr Task Board

**Read this first.** It is the live status of the project: who owns what, what is done, what is next, and what is blocked. Every person and agent updates it as they work (see the rules in `CLAUDE.md`).

- **Deadline:** Saturday, November 7, 2026, 2:00 PM Qatar time. Internal deadline: **12:30 PM**.
- **Repository:** https://github.com/arwaili/sitr-ai-gate
- **Dataset:** https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp
- **Space:** not deployed yet

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
| S8 | Create the team Hugging Face org on the website, add members, move the dataset to it; credits cannot be moved by an agent, see Blockers | Abdulaziz | | blocked | |

## Phase 3 - Ingestion and deterministic security (Saad)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| I1 | Digital PDF extraction with PyMuPDF, page mapping, Arabic preserved | Saad | | open | |
| I2 | Empty, corrupted, oversized and unsupported files fail safely; file-size and page limits; temp files removed | Saad | | open | |
| I3 | Detectors: Qatar phone, synthetic QID, passport-like ID, IBAN, account numbers, salaries (Arabic and English) | Saad | | open | |
| I4 | Secret detectors: API keys, bearer tokens, JWTs, password assignments, database URLs, private-key blocks, cloud keys, internal hosts | Saad | | open | |
| I5 | Placeholder keys in documentation (`sk-XXXX`) must not be critical; this fixes test T7 | Saad | | open | |
| I6 | Demo files: `examples/synthetic_cv.pdf`, `synthetic_contract.pdf`, `vulnerable_code.py`, `safe_prompt.txt` | Saad | | open | |
| I7 | Replace `+974 5555 01xx` demo phone numbers with a format that cannot belong to a real person | Saad | | open | |

## Phase 4 - Hugging Face intelligence (Mohammed)

| ID | Task | Owner | Claimed by | Status | PR |
|---|---|---|---|---|---|
| H1 | Load `OpenMed/privacy-filter-multilingual-v2` lazily on CPU, cached; map its labels to Sitr types; exact offsets | Mohammed | | open | |
| H2 | Semantic risk with `Horizon-Labs/multilingual-zeroshot-small`; deterministic fallback when the model fails | Mohammed | | open | |
| H3 | Evaluation script on the dataset `test` split (an HF Job if it needs a GPU): precision, recall, action accuracy, per-language results, latency | Mohammed | | open | |
| H4 | Update the dataset card wording to describe the new filter checks; check Qwen sentences for real names | Mohammed | | open | |

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

- **S8:** the team Hugging Face org must be created by Abdulaziz at https://huggingface.co/organizations/new (it cannot be created through the API). Then invite members (their HF usernames are not known yet) and move the dataset with `hf repo move` or `huggingface_hub.move_repo`. Hugging Face credits belong to the account that received them; ask the hackathon organisers to apply them to the org. Until then, jobs bill to `arwaili` (about $0.03 so far).
- `main` is not protected: the repository is private on a free plan. Follow the PR rules anyway.
- GitHub usernames are not yet matched to people, so `CODEOWNERS` is not filled in.

## Log

Newest first. One line per finished piece of work: date and time (Qatar), name, what changed, PR.

- 2026-11-06 - Abdulaziz - PRs #1, #2, #5, #3, #4 merged in order. Merged `main`: 62 tests pass plus 1 expected failure (T7); Ruff, compile, offline four-scenario check (allow, redact, private, block) and secret scan all pass; contracts unchanged since `887963c`. Clean-venv install confirmed (S7). Collaborators invited (S6).
- 2026-11-06 - Abdulaziz - Task board and team workflow added to `TASKS.md` and `CLAUDE.md`. [#1](https://github.com/arwaili/sitr-ai-gate/pull/1)
- 2026-11-06 - Abdulaziz - Dataset `arwaili/sitr-synthetic-dlp` generated with Qwen in an HF Job and published (300 examples). [#5](https://github.com/arwaili/sitr-ai-gate/pull/5)
- 2026-11-05 - Abdulaziz - Contracts locked at `887963c`; mocks for all four lanes and the Gradio shell built. PRs [#1](https://github.com/arwaili/sitr-ai-gate/pull/1) to [#5](https://github.com/arwaili/sitr-ai-gate/pull/5)
