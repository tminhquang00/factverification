"""Fit calibration-only confidence thresholds for false-contradiction/support risk diagnostics."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from scipy.stats import beta


def split_is_calibration(question_id, fraction, seed):
    digest = hashlib.sha256(f"{seed}:{question_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    return value < fraction


def clopper_pearson_upper(errors, n, delta):
    if n == 0:
        return 1.0
    if errors == n:
        return 1.0
    return float(beta.ppf(1.0 - delta, errors + 1, n - errors))


def expected_calibration_error(items, bins=10):
    if not items:
        return 0.0
    total = len(items)
    ece = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [item for item in items if low <= item["confidence"] <= high
                  and (index == bins - 1 or item["confidence"] < high)]
        if not bucket:
            continue
        accuracy = sum(item["correct"] for item in bucket) / len(bucket)
        confidence = sum(item["confidence"] for item in bucket) / len(bucket)
        ece += len(bucket) / total * abs(accuracy - confidence)
    return ece


def fit_threshold(calibration, verdict, target, delta, minimum):
    candidates = sorted({item["confidence"] for item in calibration}, reverse=True)
    curve = []
    for threshold in candidates:
        accepted = [
            item for item in calibration
            if item["prediction"] == verdict and item["confidence"] >= threshold
        ]
        errors = sum(not item["correct"] for item in accepted)
        upper = clopper_pearson_upper(errors, len(accepted), delta)
        curve.append({
            "threshold": threshold,
            "n": len(accepted),
            "errors": errors,
            "observed_risk": errors / len(accepted) if accepted else 0.0,
            "upper_bound": upper,
        })
    feasible = [item for item in curve if item["n"] >= minimum and item["upper_bound"] <= target]
    selected = max(feasible, key=lambda item: (item["n"], -item["threshold"])) if feasible else None
    return selected, curve


def evaluate_threshold(test, verdict, selected, delta):
    original = [item for item in test if item["prediction"] == verdict]
    if selected is None:
        accepted = []
        threshold = None
    else:
        threshold = selected["threshold"]
        accepted = [item for item in original if item["confidence"] >= threshold]
    errors = sum(not item["correct"] for item in accepted)
    return {
        "threshold": threshold,
        "n_original_decisions": len(original),
        "n_accepted": len(accepted),
        "decision_coverage": len(accepted) / len(original) if original else 0.0,
        "errors": errors,
        "observed_risk": errors / len(accepted) if accepted else 0.0,
        "upper_bound": clopper_pearson_upper(errors, len(accepted), delta),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--calibration_fraction", type=float, default=0.4)
    parser.add_argument("--split_seed", type=int, default=20260803)
    parser.add_argument("--target_risk", type=float, default=0.10)
    parser.add_argument("--delta", type=float, default=0.05)
    parser.add_argument("--minimum_calibration_decisions", type=int, default=30)
    parser.add_argument("--seed_filter", type=int)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for row in payload["atomic_results"]:
        if args.seed_filter is not None and row["seed"] != args.seed_filter:
            continue
        for system, prediction in row["predictions"].items():
            confidence = row.get("confidences", {}).get(system)
            if confidence is None:
                continue
            grouped[(row["generator_model"], row["detector_model"], system)].append({
                "question_id": row["question_id"],
                "prediction": prediction,
                "gold": row["gold"],
                "confidence": float(confidence),
                "correct": prediction == row["gold"],
            })

    results = {}
    for key, items in sorted(grouped.items()):
        calibration = [
            item for item in items
            if split_is_calibration(item["question_id"], args.calibration_fraction, args.split_seed)
        ]
        test = [
            item for item in items
            if not split_is_calibration(item["question_id"], args.calibration_fraction, args.split_seed)
        ]
        decisions = {}
        for verdict, label in (("Contradicted", "false_contradiction"),
                               ("Supported", "false_support")):
            selected, curve = fit_threshold(
                calibration, verdict, args.target_risk, args.delta,
                args.minimum_calibration_decisions,
            )
            decisions[label] = {
                "calibration_selected": selected,
                "test": evaluate_threshold(test, verdict, selected, args.delta),
                "risk_coverage_curve": curve,
            }
        results["__".join(key)] = {
            "n": len(items),
            "n_calibration": len(calibration),
            "n_test": len(test),
            "ece_all_rows": expected_calibration_error(items),
            "decisions": decisions,
        }

    output = {
        "protocol": {
            "calibration_fraction": args.calibration_fraction,
            "split_seed": args.split_seed,
            "target_risk": args.target_risk,
            "delta": args.delta,
            "minimum_calibration_decisions": args.minimum_calibration_decisions,
            "seed_filter": args.seed_filter,
            "warning": (
                "This is a grouped calibration/test diagnostic with binomial upper bounds, not a "
                "formal conformal guarantee: repeated atoms within questions are correlated and "
                "the confidence score was not learned on an independent human-labelled corpus."
            ),
        },
        "results": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        key: {
            "ece": value["ece_all_rows"],
            "false_contradiction_test": value["decisions"]["false_contradiction"]["test"],
            "false_support_test": value["decisions"]["false_support"]["test"],
        }
        for key, value in results.items()
    }, indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
