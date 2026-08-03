"""Rescore saved pilot atoms over every deterministic degradation condition without LLM calls."""

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kg_store import get_kg_store
from scripts.run_incompleteness_pilot import mechanical_gold_for_graph
from verification_pipeline import VerificationPipeline


def stage4_pipeline(graph_path, declaration_path, routing_mode, cwa_threshold=0.85):
    pipeline = VerificationPipeline.__new__(VerificationPipeline)
    pipeline.store = get_kg_store(str(graph_path), completeness_path=str(declaration_path))
    pipeline.routing_mode = routing_mode
    pipeline.cwa_threshold = cwa_threshold
    return pipeline


def metrics(rows):
    grouped = defaultdict(list)
    curves = defaultdict(list)
    for row in rows:
        for system, pred in row["predictions"].items():
            grouped[(row["generator_model"], row["detector_model"], row["seed"],
                     row["mode"], row["retention"],
                     row["generation_condition"], system)].append((pred, row["gold"]))
            curves[(row["generator_model"], row["detector_model"], row["seed"],
                    row["mode"], row["retention"], system)].append(
                (pred, row["gold"])
            )

    def summarize(pairs):
        contradicted = [(pred, gold) for pred, gold in pairs if pred == "Contradicted"]
        false = sum(gold in {"Supported", "Not-in-KG"} for _pred, gold in contradicted)
        return {
            "n_atoms": len(pairs),
            "accuracy": sum(pred == gold for pred, gold in pairs) / len(pairs) if pairs else 0.0,
            "false_contradiction_rate": false / len(contradicted) if contradicted else 0.0,
            "n_predicted_contradicted": len(contradicted),
            "n_false_contradictions": false,
            "gold_distribution": dict(Counter(gold for _pred, gold in pairs)),
        }

    return {
        "by_generation_condition": {
            "__".join(map(str, key)): summarize(pairs) for key, pairs in sorted(grouped.items())
        },
        "curves": {
            "__".join(map(str, key)): summarize(pairs) for key, pairs in sorted(curves.items())
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", nargs="+", required=True)
    parser.add_argument("--degradation_dir", nargs="+",
                        default=["output/experiments/nusmods_degradation"])
    parser.add_argument("--full_graph", default="data/nusmods_graph.json")
    parser.add_argument("--full_declaration", default="data/completeness_declarations/nusmods.json")
    parser.add_argument("--degraded_graph_filename", default="nusmods_graph.json")
    parser.add_argument("--occupancy_thresholds", type=float, nargs="+",
                        default=[0.50, 0.70, 0.85, 0.95])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pilot_atoms = []
    pilot_runs = []
    for path in args.pilot:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        generator_model = payload["run"].get("generator_model", payload["run"]["model"])
        detector_model = payload["run"].get("detector_model", payload["run"]["model"])
        # The pilot stores each atom at 100% and 50%. Take one canonical copy before rescoring.
        atoms = [row for row in payload["atomic_results"] if row["coverage"] == 100]
        for row in atoms:
            pilot_atoms.append((generator_model, detector_model, row))
        pilot_runs.append(payload["run"])

    scored = []
    full_graph = json.loads(Path(args.full_graph).read_text(encoding="utf-8"))
    full_pipeline = stage4_pipeline(args.full_graph, args.full_declaration, "declared")
    condition_dirs = []
    for root_value in args.degradation_dir:
        root = Path(root_value)
        condition_dirs.extend(
            path.parent for path in root.rglob("manifest.json")
            if path.parent != root and (path.parent / args.degraded_graph_filename).exists()
        )
    for condition_dir in sorted(set(condition_dirs)):
        manifest = json.loads((condition_dir / "manifest.json").read_text(encoding="utf-8"))
        graph = json.loads((condition_dir / args.degraded_graph_filename).read_text(encoding="utf-8"))
        declared = stage4_pipeline(
            condition_dir / args.degraded_graph_filename, condition_dir / "completeness.json", "declared"
        )
        occupancy_pipelines = {}
        for threshold in args.occupancy_thresholds:
            occupancy = copy.copy(declared)
            occupancy.routing_mode = "occupancy"
            occupancy.cwa_threshold = threshold
            occupancy_pipelines[threshold] = occupancy
        retention = int(round(manifest["requested_retention"] * 100))
        mode = manifest["mode"]
        seed = manifest["seed"]
        for generator_model, detector_model, atom in pilot_atoms:
            triple = tuple(atom["triple"])
            full_result = mechanical_gold_for_graph(triple, full_graph, full_pipeline.store)
            gold = mechanical_gold_for_graph(triple, graph, declared.store)
            declared_pred = declared.stage_4_verify_triple(*triple)["verdict"]
            predictions = {
                "declared": declared_pred,
                "binary": "Contradicted" if declared_pred == "Not-in-KG" else declared_pred,
            }
            for threshold, occupancy in occupancy_pipelines.items():
                predictions[f"occupancy_{threshold:.2f}"] = occupancy.stage_4_verify_triple(
                    *triple
                )["verdict"]
            entity_score = atom.get("entity_score", 1.0)
            agreement = atom.get("decomposition_agreement", 1.0)
            confidences = {
                system: (
                    declared if system in {"declared", "binary"}
                    else occupancy_pipelines[float(system.rsplit("_", 1)[1])]
                ).calculate_confidence(
                    *triple, prediction,
                    entity_score=entity_score, decomp_agreement=agreement,
                )
                for system, prediction in predictions.items()
            }
            scored.append({
                "generator_model": generator_model,
                "detector_model": detector_model,
                "question_id": atom["question_id"],
                "question_type": atom["question_type"],
                "generation_condition": atom["generation_condition"],
                "seed": seed,
                "mode": mode,
                "retention": retention,
                "claim": atom.get("claim"),
                "triple": list(triple),
                "full_graph_gold": full_result,
                "gold": gold,
                "predictions": predictions,
                "confidences": confidences,
            })

    output = {
        "pilot_runs": pilot_runs,
        "conditions": sorted({(row["seed"], row["mode"], row["retention"]) for row in scored}),
        "occupancy_thresholds": args.occupancy_thresholds,
        "summary": metrics(scored),
        "atomic_results": scored,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"]["curves"], indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
