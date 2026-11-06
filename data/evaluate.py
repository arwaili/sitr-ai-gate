"""Measure Sitr's detectors and decisions on the synthetic dataset.

    python data/evaluate.py                 # held-out test split from the Hub (final numbers)
    python data/evaluate.py --split dev     # dev split, for tuning

Entities come from Lane 1 rules plus Lane 2's model, merged by the policy engine (rules win),
and actions come from the policy engine with the semantic classifier, as in the app.
Writes data/eval_results_<split>.json.
"""

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.generate_dataset import load_published  # noqa: E402
from src import hf_detection, risk_classifier  # noqa: E402
from src.contracts import ModelMetadata  # noqa: E402
from src.deterministic import detect_deterministic  # noqa: E402
from src.hf_detection import detect_entities  # noqa: E402
from src.policy_engine import decide, merge_findings  # noqa: E402
from src.risk_classifier import classify_risk  # noqa: E402

REPO_ID = "arwaili/sitr-synthetic-dlp"
METADATA = ModelMetadata(detector=hf_detection.MODEL_ID, classifier=risk_classifier.MODEL_ID)


def _rate(hits: int, total: int) -> float:
    return round(hits / total, 3) if total else 0.0


def _ms(values: list[float]) -> dict:
    values = sorted(values)
    # Median, not mean: the first call includes loading the model.
    return {
        "median": round(statistics.median(values) * 1000),
        "p95": round(values[int(len(values) * 0.95) - 1] * 1000),
    }


def evaluate(rows: list[dict]) -> dict:
    spans = Counter()  # (type, "tp"|"fp"|"fn")
    risk, action = Counter(), Counter()  # (group, correct?)
    timings: dict[str, list[float]] = {"rules": [], "pii_model": [], "risk_model": []}
    for row in rows:
        text = row["text"]
        started = time.perf_counter()
        rules = detect_deterministic(text)
        timings["rules"].append(time.perf_counter() - started)
        started = time.perf_counter()
        model = detect_entities(text)
        timings["pii_model"].append(time.perf_counter() - started)
        started = time.perf_counter()
        prediction = classify_risk(text)
        timings["risk_model"].append(time.perf_counter() - started)

        entities = merge_findings(rules, model)
        found = {(e.start, e.end): e.entity_type for e in entities}
        gold = {(e["start"], e["end"]): e["entity_type"] for e in row["entities"]}
        for span, kind in gold.items():
            spans[(kind, "tp" if found.get(span) == kind else "fn")] += 1
        for span, kind in found.items():
            if gold.get(span) != kind:
                spans[(kind, "fp")] += 1

        decided = decide(row["id"], text, entities, METADATA, prediction).recommended_action
        for group in ("all", row["language"], row["expected_action"]):
            risk[(group, prediction.risk_level == row["expected_risk"])] += 1
            action[(group, decided == row["expected_action"])] += 1

    kinds = sorted({kind for kind, _ in spans})
    entities = {}
    for kind in kinds + ["all"]:
        tp, fp, fn = (
            sum(n for (k, outcome), n in spans.items() if outcome == o and kind in (k, "all"))
            for o in ("tp", "fp", "fn")
        )
        entities[kind] = {"precision": _rate(tp, tp + fp), "recall": _rate(tp, tp + fn),
                          "support": tp + fn}
    groups = ["all", "en", "ar", "mixed", "allow", "redact", "private", "block"]
    return {
        "examples": len(rows),
        "entities": entities,
        "action_accuracy": {g: _rate(action[(g, True)], action[(g, True)] + action[(g, False)])
                            for g in groups},
        "risk_model_accuracy": {g: _rate(risk[(g, True)], risk[(g, True)] + risk[(g, False)])
                                for g in groups},
        "latency_ms": {name: _ms(values) for name, values in timings.items()},
        "models": [hf_detection.status(), risk_classifier.status()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    parser.add_argument("--repo", default=REPO_ID)
    args = parser.parse_args()
    rows = [row for row in load_published(args.repo) if row["split"] == args.split]
    hf_detection.warm_up()
    risk_classifier.warm_up()
    results = evaluate(rows)
    output = Path(__file__).parent / f"eval_results_{args.split}.json"
    output.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
