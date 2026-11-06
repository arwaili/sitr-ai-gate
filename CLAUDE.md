# Claude Instructions - Sitr AI Gate

## Start of every session

1. `git pull` on `main` and on your branch.
2. Read `TASKS.md` first: it says who owns what, what is in progress, and what is blocked.
3. Read `PROJECT_OVERVIEW.md` (the agreed plan), `CONTRACT_NOTES.md`, `INSTRUCTIONS.md`, `README.md`, and `src/contracts.py` before editing anything.
4. Ask your human which person they are (Abdulaziz, Saad, Mohammed, or Rashid) if it is not obvious, and which task they want. Default to the open tasks in their lane.

Where documents conflict, security requirements and frozen contracts win. On who may work on what, `TASKS.md` and this file win over `PROJECT_OVERVIEW.md` and `INSTRUCTIONS.md`.

## Objective

Build an Arabic-English AI security gateway for the Qai x Hugging Face Hackathon in Qatar. Sitr inspects employee prompts and files before AI processing, detects sensitive data, and chooses one action:

- Low risk: allow
- Medium risk: redact
- High risk: private processing
- Critical risk: block

The public demo must run on Hugging Face Spaces and use synthetic data only. Use Hugging Face (models, datasets, Jobs, Spaces, the Hub) for every part it can do; "Use of Hugging Face" is a judging criterion.

## Required demo scenarios

1. Safe public text is allowed.
2. A synthetic CV containing contact details is redacted.
3. A synthetic Arabic-English contract containing salary and employee information is routed privately.
4. Source code containing a synthetic API key is blocked.

## Taking tasks

1. Anyone may take any `open` task in `TASKS.md`, including tasks in another person's lane.
2. Claim it in `TASKS.md` (your name in **Claimed by**, status `in progress`) before writing code. Never start a task someone else has claimed.
3. When your work touches files another lane owns, name that owner as the PR reviewer.

## Keeping the documents current

Update the documents as you work, not only at the end:

- **`TASKS.md`:** change the task's status when you start it, when the PR opens (`in review`, with the PR link), and when it merges (`done`). Add a line to the **Log** for every finished piece of work, and add anything that blocks you under **Blockers**. When a phase starts or finishes, or when what works in the app changes, update the **Current status** table and paragraph at the top.
- **`CONTRACT_NOTES.md`:** update it whenever a function signature, route, placeholder rule, or error behavior changes.
- **`README.md`:** update it when setup steps, models, or links change.
- Put the documentation update in the same commit or PR as the change it describes.
- When you pull and see another person's update in `TASKS.md`, keep it. On a merge conflict in `TASKS.md`, keep both sides' lines.

## Nothing is pushed until it is checked

Before **every** `git push`, in this order:

1. Run all checks and confirm they pass:
   ```bash
   python -m compileall -q src tests
   ruff check .
   pytest
   ```
2. Review the full diff (`git diff origin/<branch>...HEAD`) for unrelated changes, debug code, and secrets.
3. Confirm no real personal data, token, password, key, or ID was added. Synthetic values only.
4. Show your human a short summary of what will be pushed and the check results, then **wait for their explicit yes**. Approval covers that one push only.

If any check fails, fix it or report it. Never push failing work and never skip a check.

## Working rules

1. Treat `src/contracts.py` as frozen. Propose contract changes to all four people before editing it.
2. Do not duplicate security logic in the user interface.
3. Deterministic security rules override model predictions.
4. Critical secrets must never reach an inference model.
5. Never log raw prompts, uploaded documents, detected values, credentials, or replacement mappings.
6. Never use real personal, financial, medical, employee, or credential data.
7. Keep the application runnable after every commit.
8. Add or update tests for every behavior change.
9. Never put tokens in code, commits, or chat. Use environment variables or Space secrets.
10. Announce any Hugging Face Job or inference expected to cost more than $5 before running it, and record what you spend in the `TASKS.md` log.

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

- Never commit or push directly to `main`. Everything reaches `main` through a pull request with passing CI and one teammate's approval.
- Use your lane branch from `TASKS.md`, or `task/<short-name>` for work outside your lane.
- Pull `main` into your branch before opening a PR.
- Keep commits small and focused. Never force-push. Never rewrite someone else's working code.
- Merge order for lane PRs: setup, ingestion, intelligence, policy, then product. Run the full test suite after every merge.

## Completion format

At the end of every task, report this to your human, and use it as the PR description:

```text
Phase:
Task ID:
Person:
Branch:
Files changed:
Behavior delivered:
Tests run:
Known limitations:
Security considerations:
Contract assumptions:
TASKS.md updated: yes/no
Recommended next step:
```
