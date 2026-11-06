# Sitr Team Execution Rules

## Locked decisions

- Repository: `sitr-ai-gate`
- Visibility: private for now (`arwaili/sitr-ai-gate`); make it public for judging, synthetic data only
- Default branch: `main`
- Runtime: Python 3.11
- Product UI: Gradio on Hugging Face Spaces
- Contracts: Pydantic v2 in `src/contracts.py`
- PDF extraction: PyMuPDF
- PII model: `OpenMed/privacy-filter-multilingual-v2`
- Risk model: `Horizon-Labs/multilingual-zeroshot-small`
- Safe rewriting/demo response: `Qwen/Qwen2.5-1.5B-Instruct` through Hugging Face inference
- Quality gates: Ruff and Pytest in GitHub Actions
- Merge policy: pull request, passing CI, and one teammate approval

Do not change the stack or contracts during the hackathon unless the existing choice blocks an end-to-end demo.

## Four parallel lanes

Each lane has a default owner. Anyone may take a task in any lane by claiming it in `TASKS.md` first; the lane owner reviews PRs that touch their files.

| Lane | Default owner |
|---|---|
| 1 - Ingestion | Saad |
| 2 - Hugging Face intelligence | Mohammed |
| 3 - Policy and routing | Rashid |
| 4 - Product and deployment, coordination | Abdulaziz |

### Lane 1 - Ingestion

Owner: Saad

Branch: `feature/ingestion`

Owns:

- `src/ingestion.py`
- `src/deterministic.py`
- `examples/`
- `tests/test_ingestion.py`

Delivers text/PDF/image/code extraction plus regex and secret detection with exact source offsets. Status: done in PR #8 (no OCR; images are rejected with a clear message).

### Lane 2 - Hugging Face intelligence

Owner: Mohammed

Branch: `feature/hf-intelligence`

Owns:

- `src/hf_detection.py`
- `src/risk_classifier.py`
- `data/` (the dataset generator and `synthetic_examples.json`)
- `tests/test_detection.py`

Delivers Arabic-English contextual PII detection, semantic risk classification, model caching, fallbacks, and measured evaluation. Status: done in PR #11 (models run locally on CPU with rule fallbacks).

### Lane 3 - Policy and routing

Owner: Rashid

Branch: `feature/policy-routing`

Owns:

- `src/policy_engine.py`
- `src/redactor.py`
- `src/router.py`
- `src/audit.py`
- `src/orchestrator.py`
- `tests/test_policy.py`

Delivers deterministic allow/redact/private/block decisions and the single public `inspect_and_process` entry point. Status: done in PR #14.

### Lane 4 - Product and deployment

Owner: Abdulaziz

Branch: `feature/product`

Owns:

- `app.py`
- `requirements.txt`
- `README.md`
- `assets/`
- `space/`
- `tests/test_end_to_end.py`
- Hugging Face Space deployment
- Demo, backup recording, pitch, and submission

Delivers the polished interface and complete integration.

## Integration rules

1. `src/contracts.py` is frozen. Any change requires all four members.
2. Every lane starts with mocks and builds against the shared contracts.
3. Anyone may work on another lane's task after claiming it in `TASKS.md`; that lane's owner reviews the PR.
4. Merge order is setup, ingestion, intelligence, policy, then product.
5. Run all tests after each merge.
6. Keep `TASKS.md` current: status changes, PR links, blockers, and a log line for every finished piece of work. Synchronize every three hours using: working, next, blocker, contract request, and credits spent.
7. Nothing is pushed until `compileall`, Ruff and Pytest pass, the diff is reviewed, and the person running the agent approves the push (see `CLAUDE.md`).
8. Never log or commit raw prompts, documents, secrets, tokens, or replacement values.
9. Use only synthetic identities, documents, and credentials.

## Required scenarios

| Scenario | Risk | Action |
|---|---|---|
| Public marketing prompt | Low | Allow |
| Synthetic CV with contact information | Medium | Redact |
| Synthetic Arabic-English contract | High | Private |
| Code with a synthetic API key | Critical | Block |

All four must pass on the deployed Hugging Face Space before additional features are added.

## GitHub setup

Done: the repository is pushed, the four lane branches exist from contract commit `887963c`, CI runs on every PR, the Phase 1-2 PRs (#1-#5), Phase 3 (#8), Phase 4 (#11) and Phase 5 (#14) are merged into `main`, and `malaliQA`, `astro0707-c` and `ralkubai` are invited as collaborators with write access. The four lane branches were fast-forwarded to the merged `main`.

Still to do (tracked in `TASKS.md`):

1. Protect `main` (needs a public repository or a paid plan): require pull requests, one approval, and passing CI; disable force pushes and branch deletion.
2. Add the Hugging Face token as a Space secret; never commit it.
3. Add the four GitHub usernames to `CODEOWNERS` when known.

## Agent usage

Give Claude Code or Codex one task from `TASKS.md` at a time. The agent reads `CLAUDE.md` automatically, which tells it to read the task board, claim the task, keep the documents current, and get approval before pushing. Require every agent to report in the completion format from `CLAUDE.md`. Use a second agent for review and threat modeling, not concurrent edits to the same file.

## Definition of done

- All four scenarios work end to end.
- Arabic and English are demonstrated.
- CI passes.
- The public Space contains no real sensitive data.
- Failure paths are safe and understandable.
- Hugging Face model IDs and usage are visible.
- The live demo completes in 75-90 seconds.
- A backup video or screenshots exist.

