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
    # Convention-free safety counters. `true_world_claims` counts atoms whose claim is true in the
    # reference (undegraded) graph; `contradicted_true_world` counts how many of those the system
    # called Contradicted. Their ratio needs no assumption about how absence ought to be labelled,
    # so it stays meaningful even to a reader who rejects our gold convention entirely.
    "true_world_claims",
    "contradicted_true_world",
)


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize_pairs(predictions, golds, world_truths=None):
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
        **_true_world_metrics(predictions, world_truths),
    }


def _true_world_metrics(predictions, world_truths):
    """Safety metrics restricted to claims that are true in the reference world.

    Unlike false-contradiction rate, this does not depend on any convention about what an absent
    fact ought to be labelled. It answers a question with only one defensible answer: how often did
    the system announce a contradiction about something that is, in fact, true?
    """
    if world_truths is None:
        return {}
    true_world = [
        prediction for prediction, world in zip(predictions, world_truths) if world == "true"
    ]
    contradicted = sum(prediction == "Contradicted" for prediction in true_world)
    return {
        "n_true_world_claims": len(true_world),
        "n_contradicted_true_world_claims": contradicted,
        "contradiction_rate_on_true_claims": safe_ratio(contradicted, len(true_world)),
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
        is_true_world = row.get("world_truth") == "true"
        values[7] += is_true_world
        values[8] += is_true_world and prediction == "Contradicted"
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
        "contradiction_rate_on_true_claims": divide(totals[:, 8], totals[:, 7]),
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
    for metric in ("accuracy", "false_contradiction_rate", "false_support_rate",
                   "contradiction_rate_on_true_claims"):
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
        world_truths = [row.get("world_truth") for row in group_rows]
        summary = summarize_pairs(predictions, golds, world_truths)
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
        # Contrast every system against the perfectly-maintained-metadata upper bound, and also
        # pair the realistic stale-metadata arm against the no-metadata arm. The latter is the
        # comparison that carries real information: both systems can emit contradictions from
        # absence, and neither of them defines the gold.
        for reference in ("declared_oracle", "declared"):
            if reference in systems:
                pairs.extend(
                    (reference, system) for system in systems if system != reference
                )
                break
        if "declared_stale" in systems and "binary" in systems:
            pairs.append(("declared_stale", "binary"))
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
            "gold_independence": payload.get("gold_definition", {}),
            "metric_reading_guide": {
                "false_contradiction_rate": (
                    "Contradictions issued against a gold of Supported or Not-in-KG. Depends on the "
                    "convention that absence never licenses a contradiction."
                ),
                "contradiction_rate_on_true_claims": (
                    "Contradictions issued against claims that are true in the reference world. "
                    "Convention-free; prefer this as the headline safety number."
                ),
                "declared_oracle_caveat": (
                    "declared_oracle consumes a completeness declaration regenerated for the exact "
                    "damage applied, so it cannot emit a contradiction from absence and its zero "
                    "rates are definitional. Treat it as an upper bound, never as a result."
                ),
            },
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
