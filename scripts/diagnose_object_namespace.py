"""Diagnose stage-3 object-position namespace handling on an open-domain KG.

Background
----------
Entity records are keyed by id (a Q-id on CoDEx) while their field values are stored as
surface labels. Stage 3 previously substituted the resolved entity *key* for the claim's
object, so stage 4 compared an id against a label and reported a value mismatch for every
genuinely true claim. `Supported` recall on CoDEx was 0.039.

This script isolates stages 3-4 with no LLM, so the numbers reflect graph handling alone.

Two correctness requirements this script enforces
-------------------------------------------------
1. It reconstructs the ASSERTED triple from `text`, not from the `triples` field. In
   `codex_test.jsonl` the `triples` field holds the *true* edge for `Contradicted` rows,
   so feeding it directly hands the verifier the answer and makes the contradiction class
   look solved.
2. It reports per-class precision and recall, not just accuracy. The defect is invisible in
   accuracy because the misdirected mass lands on whichever class the graph happens to favour.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\diagnose_object_namespace.py
    & .venv\\Scripts\\python.exe scripts\\diagnose_object_namespace.py --thresholds 0.35 0.95
"""

import argparse
import collections
import json
import logging
import re
from pathlib import Path

from verification_pipeline import VerificationPipeline

logger = logging.getLogger("diagnose_object_namespace")

# Surface templates used by the CoDEx claim generator.
TEMPLATES = [
    re.compile(r"^The (?P<rel>.+?) of (?P<subj>.+?) is (?P<obj>.+?)\.$"),
    re.compile(r"^(?P<subj>.+?) is a member of (?P<obj>.+?)\.$"),
    re.compile(r"^(?P<subj>.+?) is located in (?P<obj>.+?)\.$"),
]
CLASSES = ["Supported", "Contradicted", "Not-in-KG"]


class _NoLLM:
    """Stage 2 must never run here; a call indicates the harness wiring is wrong."""

    model = "none"
    provider = "none"

    def generate_json(self, *args, **kwargs):
        raise AssertionError("Stage 2 was invoked; this diagnostic must not call an LLM.")


def load_asserted_items(path: Path, limit: int):
    """Returns (gold, subject, relation, asserted_object) tuples parsed from `text`."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[:limit]
    items, unparsed = [], 0
    for row in rows:
        triples = row.get("triples") or []
        if not triples:
            unparsed += 1
            continue
        subject, relation = str(triples[0][0]), str(triples[0][1])
        for template in TEMPLATES:
            match = template.match(row["text"])
            if match:
                items.append((row["gold_label"], subject, relation, match.group("obj")))
                break
        else:
            unparsed += 1
    return items, unparsed


def evaluate(pipeline, items):
    predictions = []
    for _, subject, relation, obj in items:
        triple = pipeline.stage_3_map_claim_to_triple(
            {"subject": subject, "relation": relation, "object": obj, "claim_type": relation}
        )
        predictions.append(pipeline.stage_4_verify_triple(*triple).get("verdict"))
    return predictions


def report(tag, items, predictions):
    golds = [g for g, _, _, _ in items]
    accuracy = sum(1 for g, p in zip(golds, predictions) if g == p) / len(items)
    print(f"\n{tag}")
    print(f"  accuracy {accuracy:.4f}   verdicts {dict(collections.Counter(predictions))}")
    for cls in CLASSES:
        support = sum(1 for g in golds if g == cls)
        predicted = sum(1 for p in predictions if p == cls)
        hits = sum(1 for g, p in zip(golds, predictions) if g == cls and p == cls)
        recall = hits / support if support else 0.0
        precision = hits / predicted if predicted else 0.0
        print(f"    {cls:14} recall {recall:.3f}   precision {precision:.3f}   support {support}")
    return accuracy


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="data/codex_test.jsonl")
    parser.add_argument("--graph", default="data/codex_graph.json")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.35, 0.95],
                        help="Entity-link thresholds to compare.")
    parser.add_argument("--out", default=None, help="Write results as JSON here.")
    args = parser.parse_args()

    items, unparsed = load_asserted_items(Path(args.dataset), args.limit)
    print(f"Asserted-triple oracle parse: {len(items)} items "
          f"({unparsed} rows dropped: no surface template matched)")

    results = {}
    for threshold in args.thresholds:
        pipeline = VerificationPipeline(
            kg_path=args.graph, llm_client=_NoLLM(), entity_link_threshold=threshold
        )
        predictions = evaluate(pipeline, items)
        results[str(threshold)] = report(f"entity_link_threshold = {threshold}", items, predictions)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "dataset": args.dataset,
            "graph": args.graph,
            "n_items": len(items),
            "n_unparsed": unparsed,
            "accuracy_by_threshold": results,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
