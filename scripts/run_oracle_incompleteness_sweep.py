"""Evaluate routing systems on expected triples across deterministic KG deletions.

This is the model-free ceiling for the incompleteness study: claim decomposition and
entity linking are replaced by the known expected triples, while Stage 4 and its
world-assumption routing remain unchanged.
"""

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.rescore_incompleteness_sweep import stage4_pipeline
from scripts.run_incompleteness_pilot import mechanical_gold_for_graph, read_jsonl


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def discover_conditions(roots, graph_filename):
    conditions = []
    for root_value in roots:
        for manifest_path in Path(root_value).rglob("manifest.json"):
            directory = manifest_path.parent
            graph_path = directory / graph_filename
            declaration_path = directory / "completeness.json"
            if not graph_path.exists() or not declaration_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not {"requested_retention", "seed", "mode", "graph_sha256"} <= manifest.keys():
                continue
            conditions.append({
                "seed": int(manifest["seed"]),
                "mode": manifest["mode"],
                "retention": int(round(float(manifest["requested_retention"]) * 100)),
                "graph": graph_path,
                "declaration": declaration_path,
                "graph_sha256": manifest["graph_sha256"],
            })
    return sorted(conditions, key=lambda row: (row["seed"], row["mode"], row["retention"]))


def oracle_confidence(verdict, relation_occupancy):
    if verdict == "Supported":
        return 1.0
    if verdict == "Contradicted":
        return relation_occupancy
    if verdict == "Not-in-KG":
        return 1.0 - relation_occupancy
    return 1.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--full_graph", required=True)
    parser.add_argument("--full_declaration", required=True)
    parser.add_argument("--degradation_dir", nargs="+", required=True)
    parser.add_argument("--degraded_graph_filename", required=True)
    parser.add_argument(
        "--occupancy_thresholds", type=float, nargs="+", default=[0.50, 0.70, 0.85, 0.95]
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    questions = read_jsonl(args.questions)
    expected = [
        (question, tuple(triple))
        for question in questions
        for triple in question.get("expected_triples", [])
    ]
    full_graph = json.loads(Path(args.full_graph).read_text(encoding="utf-8"))
    full_pipeline = stage4_pipeline(args.full_graph, args.full_declaration, "declared")
    full_gold = {
        (question["id"], index): mechanical_gold_for_graph(triple, full_graph, full_pipeline.store)
        for question in questions
        for index, triple in enumerate(map(tuple, question.get("expected_triples", [])))
    }
    question_map = {question["id"]: question for question in questions}
    unexpected_gold = {
        key: value
        for key, value in full_gold.items()
        if value != "Supported"
        and question_map[key[0]]["question_type"] != "staffing-open-world"
    }
    if unexpected_gold:
        raise ValueError(
            f"Expected factual triples are not graph facts: {list(unexpected_gold.items())[:10]}"
        )

    conditions = discover_conditions(args.degradation_dir, args.degraded_graph_filename)
    if not conditions:
        raise ValueError("no degradation conditions matched")

    rows = []
    for condition in conditions:
        graph = json.loads(condition["graph"].read_text(encoding="utf-8"))
        declared = stage4_pipeline(condition["graph"], condition["declaration"], "declared")
        occupancy = {}
        for threshold in args.occupancy_thresholds:
            variant = copy.copy(declared)
            variant.routing_mode = "occupancy"
            variant.cwa_threshold = threshold
            occupancy[threshold] = variant
        relation_occupancies = {
            relation: declared.store.estimate_relation_occupancy(relation)
            for relation in {triple[1] for _question, triple in expected}
        }
        question_atom_indices = defaultdict(int)
        for question, triple in expected:
            atom_index = question_atom_indices[question["id"]]
            question_atom_indices[question["id"]] += 1
            gold = mechanical_gold_for_graph(triple, graph, declared.store)
            declared_prediction = declared.stage_4_verify_triple(*triple)["verdict"]
            predictions = {
                "declared": declared_prediction,
                "binary": (
                    "Contradicted"
                    if declared_prediction == "Not-in-KG"
                    else declared_prediction
                ),
            }
            for threshold, pipeline in occupancy.items():
                predictions[f"occupancy_{threshold:.2f}"] = pipeline.stage_4_verify_triple(
                    *triple
                )["verdict"]
            rows.append({
                "generator_model": "oracle_expected_triples",
                "detector_model": "oracle_expected_triples",
                "question_id": question["id"],
                "question_type": question["question_type"],
                "generation_condition": "oracle_expected_triple",
                "seed": condition["seed"],
                "mode": condition["mode"],
                "retention": condition["retention"],
                "triple": list(triple),
                "full_graph_gold": full_gold[(question["id"], atom_index)],
                "gold": gold,
                "predictions": predictions,
                "confidences": {
                    system: oracle_confidence(prediction, relation_occupancies[triple[1]])
                    for system, prediction in predictions.items()
                },
            })

    output = {
        "run": {
            "questions": args.questions,
            "question_count": len(questions),
            "expected_triple_count": len(expected),
            "condition_count": len(conditions),
            "row_count": len(rows),
            "questions_sha256": file_sha256(args.questions),
            "full_graph_sha256": file_sha256(args.full_graph),
            "script_sha256": file_sha256(__file__),
            "occupancy_thresholds": args.occupancy_thresholds,
        },
        "conditions": [
            {key: value for key, value in condition.items() if key not in {"graph", "declaration"}}
            for condition in conditions
        ],
        "atomic_results": rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["run"], indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
