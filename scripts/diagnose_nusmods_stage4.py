"""Measure the stage-3/4 ceiling on the NUSMods benchmark with no LLM in the loop.

The benchmark's `asserted_triples` field holds exactly what each sentence states — the false
value on a `Contradicted` row, the absent module code on a `Not-in-KG` row. Feeding those
straight into stages 3 and 4 removes decomposition from the measurement, so whatever accuracy
this reports is the upper bound the full pipeline can reach on this benchmark, and every point
below it in an `eval_harness.py --dataset nusmods` run is attributable to stage 2.

This is also how the entity-link threshold is chosen. `Not-in-KG` rows name plausible but
non-existent module codes; below some threshold the bi-encoder links them to a real module and
the class collapses into Supported/Contradicted. The sweep reports that directly.

Note this diagnostic reads `asserted_triples`, never `triples` — the latter is the KG evidence
shown to the context baseline and holds the *true* edge on contradicted rows, so using it would
hand the verifier the answer.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\diagnose_nusmods_stage4.py
    & .venv\\Scripts\\python.exe scripts\\diagnose_nusmods_stage4.py --thresholds 0.35 0.80 0.95
"""

import argparse
import collections
import json
from pathlib import Path

from verification_pipeline import VerificationPipeline

CLASSES = ["Supported", "Contradicted", "Not-in-KG"]


class _NoLLM:
    """Stage 2 must never run here; a call means the harness wiring is wrong."""

    model = "none"
    provider = "none"

    def generate_json(self, *args, **kwargs):
        raise AssertionError("Stage 2 was invoked; this diagnostic must not call an LLM.")


def load_rows(path: Path, limit: int):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    missing = [row["id"] for row in rows if not row.get("asserted_triples")]
    if missing:
        raise ValueError(f"{len(missing)} rows carry no asserted_triples (first: {missing[0]}). "
                         "Regenerate with scripts/build_nusmods_benchmark.py.")
    return rows[:limit]


def predict(pipeline, row):
    """Runs every asserted triple through stages 3-4 and combines verdicts as the pipeline does."""
    verdicts = []
    for subject, relation, obj in row["asserted_triples"]:
        triple = pipeline.stage_3_map_claim_to_triple(
            {"subject": subject, "relation": relation, "object": obj, "claim_type": relation}
        )
        verdicts.append(pipeline.stage_4_verify_triple(*triple).get("verdict"))

    for verdict in ("Contradicted", "Not-in-KG", "Out-of-scope"):
        if verdict in verdicts:
            return "Not-in-KG" if verdict == "Out-of-scope" else verdict
    return "Supported"


def report(tag, rows, predictions):
    golds = [row["gold_label"] for row in rows]
    accuracy = sum(1 for g, p in zip(golds, predictions) if g == p) / len(rows)
    print(f"\n{tag}")
    print(f"  accuracy {accuracy:.4f}   verdicts {dict(collections.Counter(predictions))}")
    for cls in CLASSES:
        support = sum(1 for g in golds if g == cls)
        predicted = sum(1 for p in predictions if p == cls)
        hits = sum(1 for g, p in zip(golds, predictions) if g == cls and p == cls)
        print(f"    {cls:14} recall {hits / support if support else 0:.3f}   "
              f"precision {hits / predicted if predicted else 0:.3f}   support {support}")

    print("  by reasoning type:")
    for r_type in sorted({row["reasoning_type"] for row in rows}):
        subset = [(row, p) for row, p in zip(rows, predictions) if row["reasoning_type"] == r_type]
        hits = sum(1 for row, p in subset if row["gold_label"] == p)
        print(f"    {r_type:28} {hits}/{len(subset)}  {hits / len(subset):.3f}")
    return accuracy


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="data/nusmods_test.jsonl")
    parser.add_argument("--graph", default="data/nusmods_graph.json")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.35, 0.95])
    parser.add_argument("--out", default=None, help="Write results as JSON here.")
    args = parser.parse_args()

    rows = load_rows(Path(args.dataset), args.limit)
    floor = max(collections.Counter(r["gold_label"] for r in rows).values()) / len(rows)
    print(f"NUSMods stage-3/4 ceiling on {len(rows)} rows (majority-class floor {floor:.2%})")

    results = {}
    for threshold in args.thresholds:
        pipeline = VerificationPipeline(kg_path=args.graph, llm_client=_NoLLM(),
                                        entity_link_threshold=threshold)
        predictions = [predict(pipeline, row) for row in rows]
        results[str(threshold)] = report(f"entity_link_threshold = {threshold}", rows, predictions)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "dataset": args.dataset,
            "graph": args.graph,
            "n_items": len(rows),
            "majority_floor": floor,
            "accuracy_by_threshold": results,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
