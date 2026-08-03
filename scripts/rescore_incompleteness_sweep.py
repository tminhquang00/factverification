"""Rescore saved pilot atoms over every deterministic degradation condition without LLM calls.

Gold labels come from :mod:`scripts.intervention_gold`, which reads only the reference (full) graph
and the condition graph. No completeness declaration is consulted when building gold. This is the
change that makes the comparison informative: a declaration is now a *system input* that can be
correct, stale, or absent, and the score can tell those apart.

Four routing systems are run, each as its own pass over the graph. None is derived from another by
relabelling:

``declared_oracle``
    The companion declaration written beside each degraded graph by the degradation builder. It is
    always perfectly synchronised with the damage we caused, so it is an **upper bound**, not a
    deployable system. Reported to show what perfectly maintained completeness metadata would buy.

``declared_stale``
    The declaration for the *full* snapshot applied to a *degraded* graph. This models the realistic
    failure: catalogue metadata still says "credits are complete" while 50% of the credit facts have
    silently gone. This is the arm that carries the interesting number.

``binary``
    A verifier with no third label at all, run through ``routing_mode="binary"``. Models an external
    binary fact checker. Lower bound.

``occupancy_<t>``
    Infers open/closed from the observed density of the relation in the damaged graph, at several
    thresholds.
"""

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kg_store import get_kg_store
from scripts.intervention_gold import intervention_gold
from verification_pipeline import VerificationPipeline


def stage4_pipeline(graph_path, declaration_path, routing_mode, cwa_threshold=0.85):
    pipeline = VerificationPipeline.__new__(VerificationPipeline)
    pipeline.store = get_kg_store(str(graph_path), completeness_path=str(declaration_path))
    pipeline.routing_mode = routing_mode
    pipeline.cwa_threshold = cwa_threshold
    pipeline._missing_declaration_warned = set()
    return pipeline


def metrics(rows):
    grouped = defaultdict(list)
    curves = defaultdict(list)
    for row in rows:
        for system, pred in row["predictions"].items():
            record = (pred, row["gold"], row["world_truth"])
            grouped[(row["generator_model"], row["detector_model"], row["seed"],
                     row["mode"], row["retention"],
                     row["generation_condition"], system)].append(record)
            curves[(row["generator_model"], row["detector_model"], row["seed"],
                    row["mode"], row["retention"], system)].append(record)

    def summarize(triples):
        contradicted = [item for item in triples if item[0] == "Contradicted"]
        # Convention-dependent: a contradiction against a gold of Supported or Not-in-KG.
        false = sum(gold in {"Supported", "Not-in-KG"} for _pred, gold, _world in contradicted)
        # Convention-free: a contradiction against a claim that is TRUE in the reference world.
        # This needs no assumption about how absence should be labelled.
        true_world = [item for item in triples if item[2] == "true"]
        false_on_true = sum(pred == "Contradicted" for pred, _gold, _world in true_world)
        return {
            "n_atoms": len(triples),
            "accuracy": sum(pred == gold for pred, gold, _w in triples) / len(triples) if triples else 0.0,
            "false_contradiction_rate": false / len(contradicted) if contradicted else None,
            "n_predicted_contradicted": len(contradicted),
            "n_false_contradictions": false,
            "contradiction_rate_on_true_claims": (
                false_on_true / len(true_world) if true_world else None
            ),
            "n_true_world_claims": len(true_world),
            "n_contradicted_true_world_claims": false_on_true,
            "gold_distribution": dict(Counter(gold for _pred, gold, _w in triples)),
            "world_truth_distribution": dict(Counter(world for _p, _g, world in triples)),
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
    anomalies = Counter()
    full_graph = json.loads(Path(args.full_graph).read_text(encoding="utf-8"))
    condition_dirs = []
    for root_value in args.degradation_dir:
        root = Path(root_value)
        condition_dirs.extend(
            path.parent for path in root.rglob("manifest.json")
            if path.parent != root and (path.parent / args.degraded_graph_filename).exists()
        )
    for condition_dir in sorted(set(condition_dirs)):
        manifest = json.loads((condition_dir / "manifest.json").read_text(encoding="utf-8"))
        graph_path = condition_dir / args.degraded_graph_filename
        graph = json.loads(graph_path.read_text(encoding="utf-8"))

        # Perfectly maintained metadata: the declaration the builder wrote for this exact damage.
        declared_oracle = stage4_pipeline(graph_path, condition_dir / "completeness.json", "declared")
        # Realistic metadata: the full-snapshot declaration, never updated after the data loss.
        declared_stale = stage4_pipeline(graph_path, args.full_declaration, "declared")
        # No completeness metadata and no third label.
        binary = stage4_pipeline(graph_path, args.full_declaration, "binary")

        occupancy_pipelines = {}
        for threshold in args.occupancy_thresholds:
            occupancy = copy.copy(declared_oracle)
            occupancy.routing_mode = "occupancy"
            occupancy.cwa_threshold = threshold
            occupancy_pipelines[threshold] = occupancy

        retention = int(round(manifest["requested_retention"] * 100))
        mode = manifest["mode"]
        seed = manifest["seed"]
        for generator_model, detector_model, atom in pilot_atoms:
            triple = tuple(atom["triple"])
            gold_record = intervention_gold(triple, full_graph, graph)
            if gold_record["anomaly"]:
                anomalies[gold_record["anomaly"]] += 1

            predictions = {
                "declared_oracle": declared_oracle.stage_4_verify_triple(*triple)["verdict"],
                "declared_stale": declared_stale.stage_4_verify_triple(*triple)["verdict"],
                "binary": binary.stage_4_verify_triple(*triple)["verdict"],
            }
            for threshold, occupancy in occupancy_pipelines.items():
                predictions[f"occupancy_{threshold:.2f}"] = occupancy.stage_4_verify_triple(
                    *triple
                )["verdict"]

            entity_score = atom.get("entity_score", 1.0)
            agreement = atom.get("decomposition_agreement", 1.0)
            confidence_sources = {
                "declared_oracle": declared_oracle,
                "declared_stale": declared_stale,
                "binary": binary,
            }
            confidences = {
                system: confidence_sources.get(
                    system,
                    occupancy_pipelines.get(float(system.rsplit("_", 1)[1]))
                    if system.startswith("occupancy_") else declared_oracle,
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
                "gold": gold_record["verdict"],
                "world_truth": gold_record["world_truth"],
                "evidence_state": gold_record["evidence_state"],
                "gold_basis": gold_record["basis"],
                "gold_anomaly": gold_record["anomaly"],
                "predictions": predictions,
                "confidences": confidences,
            })

    output = {
        "gold_definition": {
            "module": "scripts/intervention_gold.py",
            "inputs": ["full reference graph", "condition graph"],
            "reads_completeness_declaration": False,
            "note": (
                "Gold is independent of every routing system under test. declared_oracle is an "
                "upper bound whose zero false-contradiction rate is definitional, not empirical; "
                "declared_stale, binary and occupancy_* are the informative arms."
            ),
        },
        "systems": ["declared_oracle", "declared_stale", "binary"]
        + [f"occupancy_{t:.2f}" for t in args.occupancy_thresholds],
        "pilot_runs": pilot_runs,
        "conditions": sorted({(row["seed"], row["mode"], row["retention"]) for row in scored}),
        "occupancy_thresholds": args.occupancy_thresholds,
        "gold_anomalies": dict(anomalies),
        "summary": metrics(scored),
        "atomic_results": scored,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"]["curves"], indent=2))
    print(f"gold anomalies: {dict(anomalies) or 'none'}")
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
