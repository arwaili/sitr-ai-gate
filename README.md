# Sitr AI Gate

Sitr is an Arabic-English AI security gateway that inspects employee prompts and files before AI processing. It detects sensitive information and chooses one of four policy actions: allow, redact, route privately, or block.

## Hackathon MVP

The live demo covers four synthetic scenarios:

1. Safe public text is allowed.
2. A synthetic CV is redacted.
3. A synthetic contract is routed to private processing.
4. Source code containing a synthetic API key is blocked.

## Locked stack

- Python 3.11
- Gradio for the Hugging Face Space
- Pydantic v2 for shared contracts
- PyMuPDF for PDF extraction
- Hugging Face Transformers and Hub
- `OpenMed/privacy-filter-multilingual-v2` for Arabic-English PII detection
- `Horizon-Labs/multilingual-zeroshot-small` for semantic risk classification
- `Qwen/Qwen2.5-1.5B-Instruct` through Hugging Face inference for safe rewriting and demo responses
- Pytest and Ruff in GitHub Actions

All examples are synthetic. Do not upload real confidential data to the public demonstration.

## GitHub workflow

- `main` is protected and always deployable.
- Work happens on `feature/ingestion`, `feature/hf-intelligence`, `feature/policy-routing`, and `feature/product`.
- Every change reaches `main` through a pull request.
- Pull requests require passing CI and one teammate review.
- Shared contract changes require approval from all four team members.

See `INSTRUCTIONS.md` after repository setup for the full ownership and integration plan.

