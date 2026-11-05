# Sitr Team Execution Rules

## Locked decisions

- Repository: `sitr-ai-gate`
- Visibility: public for the hackathon, containing synthetic data only
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

### Lane 1 - Ingestion

Branch: `feature/ingestion`

Owns:

- `src/ingestion.py`
- `src/deterministic.py`
- `examples/`
- `tests/test_ingestion.py`

Delivers text/PDF/image/code extraction plus regex and secret detection with exact source offsets.

### Lane 2 - Hugging Face intelligence

Branch: `feature/hf-intelligence`

Owns:

- `src/hf_detection.py`
- `src/risk_classifier.py`
- `data/synthetic_examples.json`
- `tests/test_detection.py`

Delivers Arabic-English contextual PII detection, semantic risk classification, model caching, fallbacks, and measured evaluation.

### Lane 3 - Policy and routing

Branch: `feature/policy-routing`

Owns:

- `src/policy_engine.py`
- `src/redactor.py`
- `src/router.py`
- `src/audit.py`
- `src/orchestrator.py`
- `tests/test_policy.py`

Delivers deterministic allow/redact/private/block decisions and the single public `inspect_and_process` entry point.

### Lane 4 - Product and deployment

Branch: `feature/product`

Owns:

- `app.py`
- `requirements.txt`
- `README.md`
- `assets/`
- `tests/test_end_to_end.py`
- Hugging Face Space deployment
- Demo, backup recording, pitch, and submission

Delivers the polished interface and complete integration.

## Integration rules

1. `src/contracts.py` is frozen. Any change requires all four members.
2. Every lane starts with mocks and builds against the shared contracts.
3. No one edits files owned by another lane without approval.
4. Merge order is ingestion, intelligence, policy, then product.
5. Run all tests after each merge.
6. Synchronize every three hours using: working, next, blocker, contract request, and credits spent.
7. Never log or commit raw prompts, documents, secrets, tokens, or replacement values.
8. Use only synthetic identities, documents, and credentials.

## Required scenarios

| Scenario | Risk | Action |
|---|---|---|
| Public marketing prompt | Low | Allow |
| Synthetic CV with contact information | Medium | Redact |
| Synthetic Arabic-English contract | High | Private |
| Code with a synthetic API key | Critical | Block |

All four must pass on the deployed Hugging Face Space before additional features are added.

## GitHub setup

After the repository is pushed:

1. Add all four members as collaborators.
2. Protect `main`.
3. Require pull requests, one approval, and passing CI.
4. Disable force pushes and branch deletion on `main`.
5. Add the Hugging Face token as a repository or Space secret; never commit it.
6. Create the four feature branches from the same `main` commit.
7. Add the four GitHub usernames to `CODEOWNERS` when known.

## Agent usage

Give Claude Code or Codex only one lane at a time. Include this file, the exact owned files, and the shared contracts. Require every agent to report files changed, tests run, limitations, and contract assumptions. Use a second agent for review and threat modeling, not concurrent edits to the same file.

## Definition of done

- All four scenarios work end to end.
- Arabic and English are demonstrated.
- CI passes.
- The public Space contains no real sensitive data.
- Failure paths are safe and understandable.
- Hugging Face model IDs and usage are visible.
- The live demo completes in 75-90 seconds.
- A backup video or screenshots exist.

