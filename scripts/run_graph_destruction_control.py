import argparse
import copy
import hashlib
import json
import random
import sys
import platform
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from answer_completeness import AnswerCompletenessVerifier, QueryIntent, QuerySpec
from kg_store import KGStore


def _json_hash(data) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _derange(values, seed: int, max_attempts: int = 10000):
    if len(values) < 2:
        raise ValueError("At least two relation objects are required for a derangement.")
    random_generator = random.Random(seed)
    candidate = list(values)
    for _ in range(max_attempts):
        random_generator.shuffle(candidate)
        if all(original != shuffled for original, shuffled in zip(values, candidate)):
            return list(candidate)
    raise ValueError("Could not construct a zero-fixed-point relation-object derangement.")


def destroy_prerequisite_graph(graph, condition: str, seed: int = 0):
    destroyed = copy.deepcopy(graph)
    edge_locations = []
    objects = []
    for subject_id in sorted(destroyed):
        for index, prerequisite in enumerate(destroyed[subject_id].get("prerequisites", [])):
            edge_locations.append((subject_id, index))
            objects.append(str(prerequisite["course_id"]))

    if condition == "empty":
        for course in destroyed.values():
            course["prerequisites"] = []
    elif condition == "shuffled":
        shuffled_objects = _derange(objects, seed=seed)
        for (subject_id, index), object_id in zip(edge_locations, shuffled_objects):
            destroyed[subject_id]["prerequisites"][index]["course_id"] = object_id
        if Counter(objects) != Counter(shuffled_objects):
            raise AssertionError("Graph destruction changed the prerequisite object multiset.")
    elif condition != "baseline":
        raise ValueError(f"Unsupported graph condition: {condition}")

    return destroyed


def _store_for_graph(graph) -> KGStore:
    store = object.__new__(KGStore)
    store.graph_json_path = "in-memory"
    store.courses = graph
    return store


def _classification_metrics(rows):
    total = len(rows)
    correct = sum(row["predicted_completeness"] == row["gold_completeness"] for row in rows)
    true_positive = sum(
        row["predicted_completeness"] == "incomplete" and row["gold_completeness"] == "incomplete"
        for row in rows
    )
    false_positive = sum(
        row["predicted_completeness"] == "incomplete" and row["gold_completeness"] != "incomplete"
        for row in rows
    )
    false_negative = sum(
        row["predicted_completeness"] != "incomplete" and row["gold_completeness"] == "incomplete"
        for row in rows
    )
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": total,
        "accuracy": correct / total if total else 0.0,
        "incomplete_precision": precision,
        "incomplete_recall": recall,
        "incomplete_f1": f1,
    }


def _clustered_accuracy_drop_ci(baseline_rows, condition_rows, seed: int, resamples: int = 1000):
    baseline_by_id = {row["id"]: row for row in baseline_rows}
    condition_by_id = {row["id"]: row for row in condition_rows}
    if set(baseline_by_id) != set(condition_by_id):
        raise ValueError("Paired conditions must contain the same example IDs.")

    subject_to_ids = {}
    for row in baseline_rows:
        subject_to_ids.setdefault(row["subject_id"], []).append(row["id"])
    subjects = sorted(subject_to_ids)
    random_generator = random.Random(seed)
    drops = []
    for _ in range(resamples):
        sampled_subjects = [random_generator.choice(subjects) for _ in subjects]
        sampled_ids = [
            record_id
            for subject_id in sampled_subjects
            for record_id in subject_to_ids[subject_id]
        ]
        baseline_accuracy = sum(
            baseline_by_id[record_id]["predicted_completeness"]
            == baseline_by_id[record_id]["gold_completeness"]
            for record_id in sampled_ids
        ) / len(sampled_ids)
        condition_accuracy = sum(
            condition_by_id[record_id]["predicted_completeness"]
            == condition_by_id[record_id]["gold_completeness"]
            for record_id in sampled_ids
        ) / len(sampled_ids)
        drops.append(baseline_accuracy - condition_accuracy)

    drops.sort()
    lower_index = int(0.025 * resamples)
    upper_index = min(resamples - 1, int(0.975 * resamples))
    return {
        "clustered_bootstrap_mean_accuracy_drop": sum(drops) / len(drops),
        "clustered_bootstrap_ci_95": [drops[lower_index], drops[upper_index]],
        "bootstrap_resamples": resamples,
        "cluster_unit": "subject_id",
    }


def run_control(
    graph_path: str,
    benchmark_path: str,
    rows_path: str,
    summary_path: str,
    seeds,
    split: str = "test",
):
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    benchmark = [
        json.loads(line)
        for line in Path(benchmark_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected_records = [record for record in benchmark if record["split"] == split]
    conditions = [("baseline", 0), ("empty", 0)] + [("shuffled", seed) for seed in seeds]
    rows = []

    for condition, seed in conditions:
        condition_graph = destroy_prerequisite_graph(graph, condition=condition, seed=seed)
        condition_hash = _json_hash(condition_graph)
        verifier = AnswerCompletenessVerifier(_store_for_graph(condition_graph))
        for record in selected_records:
            query_spec = record["query_spec"]
            spec = QuerySpec(
                intent=QueryIntent(query_spec["intent"]),
                subject_id=query_spec["subject_id"],
                kg_version=condition_hash,
                scope=query_spec.get("scope", {}),
            )
            result = verifier.verify(spec, record["candidate_response"])
            rows.append(
                {
                    "id": record["id"],
                    "subject_id": spec.subject_id,
                    "split": split,
                    "condition": condition,
                    "seed": seed,
                    "graph_hash": condition_hash,
                    "gold_completeness": record["gold_completeness"],
                    "predicted_completeness": result.verdict.value,
                    "predicted_missing": sorted(result.missing),
                    "predicted_unexpected": sorted(result.unexpected),
                    "predicted_set_precision": result.set_precision,
                    "predicted_set_recall": result.set_recall,
                    "predicted_exact_set_match": result.exact_set_match,
                }
            )

    baseline_predictions = {
        row["id"]: row["predicted_completeness"]
        for row in rows
        if row["condition"] == "baseline"
    }
    baseline_rows = [row for row in rows if row["condition"] == "baseline"]
    baseline_accuracy = _classification_metrics(baseline_rows)["accuracy"]
    summaries = []
    for condition, seed in conditions:
        condition_rows = [
            row for row in rows if row["condition"] == condition and row["seed"] == seed
        ]
        metrics = _classification_metrics(condition_rows)
        metrics.update(
            {
                "condition": condition,
                "seed": seed,
                "graph_hash": condition_rows[0]["graph_hash"] if condition_rows else None,
                "prediction_change_rate_vs_baseline": sum(
                    baseline_predictions[row["id"]] != row["predicted_completeness"]
                    for row in condition_rows
                ) / len(condition_rows) if condition_rows else 0.0,
                "observed_accuracy_drop_vs_baseline": baseline_accuracy - metrics["accuracy"],
            }
        )
        metrics.update(
            _clustered_accuracy_drop_ci(
                baseline_rows,
                condition_rows,
                seed=1000 + seed,
            )
        )
        summaries.append(metrics)

    rows_file = Path(rows_path)
    rows_file.parent.mkdir(parents=True, exist_ok=True)
    with rows_file.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schema_version": 1,
        "experiment": "e0_prerequisite_graph_destruction_v0",
        "status": "candidate_component_control",
        "source_graph": graph_path,
        "source_graph_hash": _json_hash(graph),
        "benchmark": benchmark_path,
        "benchmark_hash": f"sha256:{hashlib.sha256(Path(benchmark_path).read_bytes()).hexdigest()}",
        "script_hash": f"sha256:{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}",
        "python_version": platform.python_version(),
        "split": split,
        "permutation_seeds": list(seeds),
        "row_count": len(rows),
        "condition_summaries": summaries,
        "rows_artifact": rows_path,
    }
    summary_file = Path(summary_path)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run the paired prerequisite graph-destruction control.")
    parser.add_argument("--graph", default="data/rmit_graph.json")
    parser.add_argument("--benchmark", default="data/advising/rmit_prerequisite_completeness_v0.jsonl")
    parser.add_argument("--rows", default="output/experiments/e0_prerequisite_graph_destruction_v0.rows.jsonl")
    parser.add_argument("--summary", default="output/experiments/e0_prerequisite_graph_destruction_v0.summary.json")
    parser.add_argument("--split", default="test", choices=["development", "calibration", "test"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 23, 37, 53, 71])
    args = parser.parse_args()
    summary = run_control(
        args.graph,
        args.benchmark,
        args.rows,
        args.summary,
        args.seeds,
        split=args.split,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()