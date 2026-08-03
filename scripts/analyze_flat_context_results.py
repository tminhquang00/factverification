"""Summarize flat-context incompleteness baselines with clustered bootstrap CIs."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


LABELS = ("Supported", "Contradicted", "Not-in-KG")


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def percentile(values: list[float], probability: float) -> float:
    values = sorted(values)
    position = probability * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def macro_f1(rows: list[dict], prediction_field: str) -> float:
    scores = []
    for label in LABELS:
        true_positive = sum(
            row["gold"] == label and row[prediction_field] == label for row in rows
        )
        false_positive = sum(
            row["gold"] != label and row[prediction_field] == label for row in rows
        )
        false_negative = sum(
            row["gold"] == label and row[prediction_field] != label for row in rows
        )
        denominator = 2 * true_positive + false_positive + false_negative
        if denominator:
            scores.append(2 * true_positive / denominator)
    return sum(scores) / len(scores) if scores else 0.0


def metrics(rows: list[dict]) -> dict:
    valid = [row for row in rows if not row.get("error") and row.get("prediction")]
    contradicted = [row for row in valid if row["prediction"] == "Contradicted"]
    supported = [row for row in valid if row["prediction"] == "Supported"]
    binary_contradicted = [
        row for row in valid if row["binary_prediction"] == "Contradicted"
    ]
    return {
        "row_count": len(rows),
        "valid_count": len(valid),
        "error_count": len(rows) - len(valid),
        "tristate_accuracy": safe_ratio(
            sum(row["prediction"] == row["gold"] for row in valid), len(valid)
        ),
        "tristate_macro_f1": macro_f1(valid, "prediction"),
        "predicted_contradiction_count": len(contradicted),
        "false_contradiction_rate": safe_ratio(
            sum(row["gold"] != "Contradicted" for row in contradicted),
            len(contradicted),
        ),
        "predicted_support_count": len(supported),
        "false_support_rate": safe_ratio(
            sum(row["gold"] != "Supported" for row in supported), len(supported)
        ),
        "binary_accuracy": safe_ratio(
            sum(row["binary_prediction"] == row["gold"] for row in valid), len(valid)
        ),
        "binary_predicted_contradiction_count": len(binary_contradicted),
        "binary_false_contradiction_rate": safe_ratio(
            sum(row["gold"] != "Contradicted" for row in binary_contradicted),
            len(binary_contradicted),
        ),
        "gold_distribution": dict(Counter(row["gold"] for row in valid)),
        "prediction_distribution": dict(
            Counter(row["prediction"] for row in valid)
        ),
    }


def bootstrap(rows: list[dict], *, iterations: int, seed: int) -> dict:
    by_question: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_question[row["question_id"]].append(row)
    question_ids = sorted(by_question)
    rng = random.Random(seed)
    fields = (
        "tristate_accuracy",
        "tristate_macro_f1",
        "false_contradiction_rate",
        "false_support_rate",
        "binary_accuracy",
        "binary_false_contradiction_rate",
    )
    values: dict[str, list[float]] = defaultdict(list)
    for _ in range(iterations):
        sample_ids = [rng.choice(question_ids) for _ in question_ids]
        sample_rows = [row for qid in sample_ids for row in by_question[qid]]
        result = metrics(sample_rows)
        for field in fields:
            if result[field] is not None:
                values[field].append(result[field])
    return {
        field + "_95ci": (
            [percentile(values[field], 0.025), percentile(values[field], 0.975)]
            if values[field]
            else None
        )
        for field in fields
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in payload["rows"]:
        groups[(row["mode"], int(row["retention"]))].append(row)

    conditions = []
    for index, ((mode, retention), rows) in enumerate(sorted(groups.items())):
        conditions.append({
            "mode": mode,
            "retention": retention,
            **metrics(rows),
            **bootstrap(rows, iterations=args.iterations, seed=args.seed + index),
        })
    output = {
        "source": str(Path(args.input).resolve()),
        "model": payload["run"]["model"],
        "provider": payload["run"]["provider"],
        "bootstrap": {
            "unit": "question_id",
            "iterations": args.iterations,
            "seed": args.seed,
        },
        "baseline_scope": (
            "Oracle relation-specific graph context, not an end-to-end retriever."
        ),
        "conditions": conditions,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {destination} ({len(conditions)} conditions)")


if __name__ == "__main__":
    main()
