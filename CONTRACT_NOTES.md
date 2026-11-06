# Contract Notes

`src/contracts.py` is frozen. This file records how the lanes use it, where the schema leaves a choice open. Changing anything here needs the same agreement as changing the contracts.

## Decisions

1. **Errors fail closed.** The contract requires an action and a risk even on an error. An error response has `status="error"`, `action_taken="block"`, `risk_level="critical"`, `risk_score=100`, reason code `PROCESSING_ERROR` and `model_response=None`. The UI shows the risk as "Not assessed". Error messages never include input content.
2. **`redaction` is filled in on every non-error response.** `FinalResponse` has no field for the extracted text, and the UI needs it to highlight findings in uploaded files. `redaction.original_text` is the inspected text, and `redaction.safe_text` has every finding replaced, whatever the action. On allow it equals the original. Only the router decides which of the two text versions reaches a model.
3. **Placeholders** are `[ENTITY_TYPE_N]`, numbered per type in order of first appearance. A repeated value reuses its placeholder, and overlapping findings merge into one span.

## Lane interfaces

| Lane | Function | Returns |
|---|---|---|
| 1 | `src.ingestion.ingest(text=None, file_path=None)` | `IngestionResult`, or raises `ValueError` with a safe message. Accepts text, code and text files, and digital PDFs (`input_type="pdf"`, one `PageText` per page, pages joined with `src.ingestion.PAGE_SEPARATOR`). Limits: 10 MB, 50 pages; images need OCR and are rejected |
| 1 | `src.deterministic.detect_deterministic(text, pages=None)` | `list[SensitiveEntity]` sorted by `start`; pass `IngestionResult.pages` to fill in `page`. Nested findings are dropped; documentation placeholders (`sk-XXXX`, `<your-api-key>`) are not reported |
| 2 | `src.hf_detection.detect_entities(text)` | `list[SensitiveEntity]` with `source="hf_ner"`. Types: PERSON, EMAIL, PHONE, ADDRESS, DATE_OF_BIRTH, USERNAME (medium); IBAN, ACCOUNT_NUMBER, CREDIT_CARD, NATIONAL_ID, PIN (high); PASSWORD (critical). Never raises: on failure or timeout returns `[]` and `status()` reports `unavailable` |
| 2 | `src.hf_detection.status()`, `src.risk_classifier.status()` | `{model, state, detail}`; state is `not loaded`, `ready`, `unavailable` or `disabled` (`SITR_HF_MODELS=0`) |
| 2 | `src.hf_detection.warm_up()`, `src.risk_classifier.warm_up()` | load the model in the background at app start |
| 2 | `src.risk_classifier.classify_risk(text)` | `RiskPrediction(risk_level, confidence, explanation)`. Never raises: on failure a keyword fallback answers and its explanation starts with `Fallback` |
| 3 | `src.policy_engine.decide(document_id, text, entities, metadata, semantic=None)` | `AnalysisResult`; `semantic` is an optional `RiskPrediction` that can raise the action to private, never block or lower it |
| 3 | `src.policy_engine.merge_findings(rules, model)` | rules plus the model findings that overlap no rule finding |
| 3 | `src.redactor.redact(text, entities)` | `RedactionResult` |
| 3 | `src.router.route(action, redaction, user_intent)` | model response, or `None` on block |
| 3 | `src.router.call_model(route, prompt, user_intent)` | the replaceable model adapter; never raises. `SITR_LLM=mock` returns canned text (tests set it) |
| 3 | `src.orchestrator.inspect_and_process(text=None, file_path=None, user_intent="summarize", delete_file=False)` | `FinalResponse` as a dict |

Entity offsets are Python string indices into the exact inspected text. Every occurrence is a separate entity.

## Routes

| Action | Route name | Text sent |
|---|---|---|
| allow | `approved_external` | original, to hosted Qwen through HF Inference Providers |
| redact | `sanitized_external` | `safe_text` only, to hosted Qwen |
| private | `private_simulation` | original, answered by Qwen running inside the Sitr process (never an external service); a demonstration, not an isolated environment |
| block | none | nothing |

## Dataset

The synthetic evaluation dataset is [`arwaili/sitr-synthetic-dlp`](https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp), built by `data/generate_dataset.py`. Its `test` split is used only for final measured results.
