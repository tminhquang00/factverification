"""Summarize incompleteness sweeps with question/seed-clustered bootstrap intervals."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


LABELS = ("Supported", "Contradicted", "Not-in-KG")
STAT_NAMES = (
    "n",
    "correct",
    "predicted_contradicted",
    "false_contradictions",
    "predicted_supported",
    "false_supports",
    "decisions",
)


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize_pairs(predictions, golds):
    n = len(predictions)
    correct = sum(prediction == gold for prediction, gold in zip(predictions, golds))
    pred_c = sum(prediction == "Contradicted" for prediction in predictions)
    false_c = sum(
        prediction == "Contradicted" and gold != "Contradicted"
        for prediction, gold in zip(predictions, golds)
    )
    pred_s = sum(prediction == "Supported" for prediction in predictions)
    false_s = sum(
        prediction == "Supported" and gold != "Supported"
        for prediction, gold in zip(predictions, golds)
    )
    decisions = sum(prediction != "Not-in-KG" for prediction in predictions)
    by_label = {}
    f1_values = []
    for label in LABELS:
        true_positive = sum(
            prediction == label and gold == label
            for prediction, gold in zip(predictions, golds)
        )
        predicted = sum(prediction == label for prediction in predictions)
        actual = sum(gold == label for gold in golds)
        precision = safe_ratio(true_positive, predicted)
        recall = safe_ratio(true_positive, actual)
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        if f1 is not None:
            f1_values.append(f1)
        by_label[label] = {
            "support": actual,
            "predicted": predicted,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return {
        "n_atoms": n,
        "accuracy": safe_ratio(correct, n),
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "false_contradiction_rate": safe_ratio(false_c, pred_c),
        "n_predicted_contradicted": pred_c,
        "n_false_contradictions": false_c,
        "false_support_rate": safe_ratio(false_s, pred_s),
        "n_predicted_supported": pred_s,
        "n_false_supports": false_s,
        "decision_coverage": safe_ratio(decisions, n),
        "label_metrics": by_label,
    }


def cluster_statistics(rows, system):
    clusters = defaultdict(lambda: np.zeros(len(STAT_NAMES), dtype=np.int64))
    for row in rows:
        prediction = row["predictions"][system]
        gold = row["gold"]
        values = clusters[(row["seed"], row["question_id"])]
        values[0] += 1
        values[1] += prediction == gold
        values[2] += prediction == "Contradicted"
        values[3] += prediction == "Contradicted" and gold != "Contradicted"
        values[4] += prediction == "Supported"
        values[5] += prediction == "Supported" and gold != "Supported"
        values[6] += prediction != "Not-in-KG"
    return np.stack(list(clusters.values())) if clusters else np.zeros((0, len(STAT_NAMES)))


def ratios_from_totals(totals):
    def divide(numerator, denominator):
        result = np.full(numerator.shape, np.nan, dtype=float)
        np.divide(numerator, denominator, out=result, where=denominator != 0)
        return result

    return {
        "accuracy": divide(totals[:, 1], totals[:, 0]),
        "false_contradiction_rate": divide(totals[:, 3], totals[:, 2]),
        "false_support_rate": divide(totals[:, 5], totals[:, 4]),
        "decision_coverage": divide(totals[:, 6], totals[:, 0]),
    }


def percentile_interval(values):
    finite = values[np.isfinite(values)]
    if not len(finite):
        return None
    low, high = np.percentile(finite, [2.5, 97.5])
    return [float(low), float(high)]


def bootstrap_intervals(rows, system, iterations, seed):
    stats = cluster_statistics(rows, system)
    if not len(stats):
        return {}
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(stats), size=(iterations, len(stats)))
    totals = stats[indices].sum(axis=1)
    return {
        metric: percentile_interval(values)
        for metric, values in ratios_from_totals(totals).items()
    }


def bootstrap_difference(rows, first, second, iterations, seed):
    first_stats = cluster_statistics(rows, first)
    second_stats = cluster_statistics(rows, second)
    if first_stats.shape != second_stats.shape or not len(first_stats):
        return {}
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(first_stats), size=(iterations, len(first_stats)))
    first_ratios = ratios_from_totals(first_stats[indices].sum(axis=1))
    second_ratios = ratios_from_totals(second_stats[indices].sum(axis=1))
    observed_first = ratios_from_totals(first_stats.sum(axis=0, keepdims=True))
    observed_second = ratios_from_totals(second_stats.sum(axis=0, keepdims=True))
    output = {}
    for metric in ("accuracy", "false_contradiction_rate", "false_support_rate"):
        observed = observed_first[metric][0] - observed_second[metric][0]
        differences = first_ratios[metric] - second_ratios[metric]
        output[metric] = {
            "first_minus_second": float(observed) if np.isfinite(observed) else None,
            "ci95": percentile_interval(differences),
        }
    return output


def stable_seed(base_seed, key):
    digest = hashlib.sha256((str(base_seed) + "|" + "|".join(map(str, key))).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def summarize_groups(rows, key_fields, iterations, seed):
    groups = defaultdict(list)
    for row in rows:
        for system in row["predictions"]:
            key = tuple(row[field] for field in key_fields) + (system,)
            groups[key].append(row)
    output = {}
    for key, group_rows in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        system = key[-1]
        predictions = [row["predictions"][system] for row in group_rows]
        golds = [row["gold"] for row in group_rows]
        summary = summarize_pairs(predictions, golds)
        summary["clustered_bootstrap_ci95"] = bootstrap_intervals(
            group_rows, system, iterations, stable_seed(seed, key)
        )
        output["__".join(map(str, key))] = summary
    return output


def paired_comparisons(rows, key_fields, iterations, seed):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in key_fields)].append(row)
    output = {}
    for key, group_rows in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        systems = sorted(group_rows[0]["predictions"])
        pairs = []
        if "declared" in systems:
            pairs.extend(("declared", system) for system in systems if system != "declared")
        comparisons = {}
        for first, second in pairs:
            comparison_key = f"{first}_minus_{second}"
            comparisons[comparison_key] = bootstrap_difference(
                group_rows, first, second, iterations,
                stable_seed(seed, key + (first, second)),
            )
        output["__".join(map(str, key))] = comparisons
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = payload["atomic_results"]
    detailed_fields = (
        "generator_model", "detector_model", "mode", "retention", "generation_condition"
    )
    aggregate_fields = ("generator_model", "detector_model", "mode", "retention")
    output = {
        "protocol": {
            "input": args.input,
            "iterations": args.iterations,
            "seed": args.seed,
            "cluster_unit": "(deletion seed, question_id)",
            "estimand_warning": (
                "Metrics condition on atoms extracted by the detector. Answer-level claim-extraction "
                "coverage and expected-triple recall must be read from stage-attribution outputs."
            ),
            "undefined_rate_policy": (
                "Rates with zero predicted decisions are null, never reported as zero."
            ),
        },
        "by_generation_condition": summarize_groups(
            rows, detailed_fields, args.iterations, args.seed
        ),
        "pooled_generation_conditions": summarize_groups(
            rows, aggregate_fields, args.iterations, args.seed
        ),
        "paired_system_differences": paired_comparisons(
            rows, aggregate_fields, args.iterations, args.seed
        ),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "input_rows": len(rows),
        "detailed_groups": len(output["by_generation_condition"]),
        "aggregate_groups": len(output["pooled_generation_conditions"]),
    }, indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
