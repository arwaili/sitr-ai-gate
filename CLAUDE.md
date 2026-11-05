# Claude Instructions - Sitr AI Gate

Read `PROJECT_OVERVIEW.md`, `INSTRUCTIONS.md`, `README.md`, and `src/contracts.py` completely before editing anything. `PROJECT_OVERVIEW.md` is the agreed plan and wins where documents conflict, except on security requirements and frozen contracts.

## Objective

Build an Arabic-English AI security gateway for the Qai x Hugging Face Hackathon in Qatar. Sitr inspects employee prompts and files before AI processing, detects sensitive data, and chooses one action:

- Low risk: allow
- Medium risk: redact
- High risk: private processing
- Critical risk: block

The public demo must run on Hugging Face Spaces and use synthetic data only.

## Required demo scenarios

1. Safe public text is allowed.
2. A synthetic CV containing contact details is redacted.
3. A synthetic Arabic-English contract containing salary and employee information is routed privately.
4. Source code containing a synthetic API key is blocked.

## Working rules

1. Treat `src/contracts.py` as frozen. Propose contract changes before editing it.
2. Work only on the files assigned to the active development lane in `INSTRUCTIONS.md`.
3. Do not duplicate security logic in the user interface.
4. Deterministic security rules override model predictions.
5. Critical secrets must never reach an inference model.
6. Never log raw prompts, uploaded documents, detected values, credentials, or replacement mappings.
7. Never use real personal, financial, medical, employee, or credential data.
8. Keep the application runnable after every commit.
9. Add or update tests for every behavior change.
10. Run Ruff and Pytest before declaring a task complete.

## Locked stack

- Python 3.11
- Gradio
- Pydantic v2
- PyMuPDF
- Hugging Face Transformers and Hub
- `OpenMed/privacy-filter-multilingual-v2`
- `Horizon-Labs/multilingual-zeroshot-small`
- `Qwen/Qwen2.5-1.5B-Instruct`
- Pytest and Ruff

Do not replace a locked component unless it prevents the end-to-end demo from working. Explain and measure the problem before proposing a replacement.

## Git workflow

- Never commit directly to `main`.
- Use the lane branch named in `INSTRUCTIONS.md`.
- Keep commits small and focused.
- Do not force-push.
- Before requesting a merge, report files changed, tests run, known limitations, and contract assumptions.
- All changes reach `main` through a reviewed pull request with passing CI.

## Completion format

At the end of every task, report:

```text
Lane:
Files changed:
Behavior delivered:
Tests run:
Known limitations:
Contract assumptions:
Suggested next integration step:
```

