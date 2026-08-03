"""Summarize the MiniCheck incompleteness baseline with clustered bootstrap CIs.

MiniCheck is a binary entailment model.  The experiment records both its native
Supported/Unsupported decision and the deliberately naive tri-state mapping
Unsupported -> Contradicted, which exposes the semantic error made when graph
absence is treated as contradiction.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot take a percentile of an empty sequence")
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def metrics(rows: list[dict]) -> dict:
    native_accuracy = mean(
        row["native_prediction"] == row["binary_gold"] for row in rows
    )
    mapped_accuracy = mean(row["mapped_prediction"] == row["gold"] for row in rows)
    predicted_contradictions = [
        row for row in rows if row["mapped_prediction"] == "Contradicted"
    ]
    predicted_supports = [
        row for row in rows if row["mapped_prediction"] == "Supported"
    ]
    false_contradictions = sum(
        row["gold"] != "Contradicted" for row in predicted_contradictions
    )
    false_supports = sum(row["gold"] != "Supported" for row in predicted_supports)
    return {
        "row_count": len(rows),
        "native_binary_accuracy": native_accuracy,
        "naive_tristate_accuracy": mapped_accuracy,
        "predicted_contradiction_count": len(predicted_contradictions),
        "false_contradiction_count": false_contradictions,
        "false_contradiction_rate": (
            false_contradictions / len(predicted_contradictions)
            if predicted_contradictions
            else None
        ),
        "predicted_support_count": len(predicted_supports),
        "false_support_count": false_supports,
        "false_support_rate": (
            false_supports / len(predicted_supports) if predicted_supports else None
        ),
    }


def clustered_intervals(
    rows: list[dict], *, samples: int, seed: int
) -> dict[str, list[float] | None]:
    by_question: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_question[row["question_id"]].append(row)
    question_ids = sorted(by_question)
    rng = random.Random(seed)
    bootstraps: dict[str, list[float]] = defaultdict(list)
    for _ in range(samples):
        sampled = [rng.choice(question_ids) for _ in question_ids]
        sample_rows = [row for qid in sampled for row in by_question[qid]]
        result = metrics(sample_rows)
        for name in (
            "native_binary_accuracy",
            "naive_tristate_accuracy",
            "false_contradiction_rate",
            "false_support_rate",
        ):
            value = result[name]
            if value is not None:
                bootstraps[name].append(value)
    intervals: dict[str, list[float] | None] = {}
    for name in (
        "native_binary_accuracy",
        "naive_tristate_accuracy",
        "false_contradiction_rate",
        "false_support_rate",
    ):
        values = bootstraps[name]
        intervals[name + "_95ci"] = (
            [percentile(values, 0.025), percentile(values, 0.975)]
            if values
            else None
        )
    return intervals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in payload["rows"]:
        groups[(row["mode"], int(row["retention"]))].append(row)

    conditions = []
    for index, ((mode, retention), rows) in enumerate(sorted(groups.items())):
        result = {"mode": mode, "retention": retention, **metrics(rows)}
        result.update(
            clustered_intervals(
                rows,
                samples=args.bootstrap,
                seed=args.seed + index,
            )
        )
        conditions.append(result)

    output = {
        "source": str(Path(args.input).resolve()),
        "model": payload["run"]["model"],
        "bootstrap": {
            "unit": "question_id",
            "samples": args.bootstrap,
            "seed": args.seed,
        },
        "interpretation": (
            "MiniCheck is binary. naive_tristate_accuracy maps Unsupported to "
            "Contradicted and is intentionally not a valid open-world verifier."
        ),
        "conditions": conditions,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {destination} ({len(conditions)} conditions)")


if __name__ == "__main__":
    main()
