"""Graph-destruction control for the LLM pipeline's verification path (stages 3-4).

Why this exists
---------------
Accuracy that does not move when the graph's factual content is destroyed is not evidence of
verification. Before the stage-3 object-namespace repair, shuffling every value in
`data/codex_graph.json` changed under 3% of CoDEx predictions: the pipeline was comparing an
entity id against a label, and a mismatch is a mismatch regardless of what the label says.

The control preserves graph *structure* (entity set, relation keys, per-relation value
multiset, type distribution) and destroys only the subject-value association, so any surviving
accuracy is attributable to surface form and label priors rather than to the graph.

This complements `run_graph_destruction_control.py`, which covers the deterministic
set-completeness component on RMIT. Stages 3-4 are exercised directly with no LLM, so the
control is deterministic and cheap enough to run as a gate on every pipeline change.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\run_kg_destruction_control.py `
        --entity_link_threshold 0.95 `
        --out output\\diagnostics\\codex_destruction_control.json
"""

import argparse
import collections
import copy
import hashlib
import json
import os
import random
import tempfile
from pathlib import Path

from scripts.diagnose_object_namespace import _NoLLM, evaluate, load_asserted_items
from verification_pipeline import VerificationPipeline

# Fields that carry graph scaffolding rather than open-domain facts.
RESERVED = {
    "course_id", "title", "prerequisites", "credits", "school",
    "coordinator", "coordinator_email", "description",
}


def graph_hash(graph) -> str:
    payload = json.dumps(graph, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def shuffle_within_relation(graph, seed):
    """Permutes each relation's values across entities, preserving the value multiset."""
    out = copy.deepcopy(graph)
    rng = random.Random(seed)
    by_relation = collections.defaultdict(list)
    for key, record in out.items():
        for field in record:
            if field not in RESERVED:
                by_relation[field].append(key)
    for field, keys in by_relation.items():
        values = [out[key][field] for key in keys]
        rng.shuffle(values)
        for key, value in zip(keys, values):
            out[key][field] = value
    return out


def strip_relations(graph):
    """Removes every open-domain relation, leaving the entity scaffolding intact."""
    out = copy.deepcopy(graph)
    for record in out.values():
        for field in [f for f in record if f not in RESERVED]:
            del record[field]
    return out


def run(graph, items, threshold):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "graph.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(graph, handle)
        pipeline = VerificationPipeline(
            kg_path=path, llm_client=_NoLLM(), entity_link_threshold=threshold
        )
        predictions = evaluate(pipeline, items)
    golds = [g for g, _, _, _ in items]
    accuracy = sum(1 for g, p in zip(golds, predictions) if g == p) / len(items)
    return accuracy, predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="data/codex_test.jsonl")
    parser.add_argument("--graph", default="data/codex_graph.json")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 23, 37, 53, 71])
    parser.add_argument("--entity_link_threshold", type=float, default=0.95)
    parser.add_argument("--min_change_rate", type=float, default=0.20,
                        help="Acceptance gate: prediction change rate under shuffle must exceed this.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    items, unparsed = load_asserted_items(Path(args.dataset), args.limit)
    base_graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    print(f"Graph-destruction control on {args.dataset}: n={len(items)} ({unparsed} unparsed), "
          f"entity_link_threshold={args.entity_link_threshold}\n")

    baseline_acc, baseline_preds = run(base_graph, items, args.entity_link_threshold)
    conditions = [{
        "condition": "baseline", "seed": None, "accuracy": baseline_acc,
        "accuracy_drop": 0.0, "prediction_change_rate": 0.0,
        "graph_hash": graph_hash(base_graph),
    }]
    print(f"  {'baseline':22} acc={baseline_acc:.4f}")

    change_rates = []
    for seed in args.seeds:
        graph = shuffle_within_relation(base_graph, seed)
        acc, preds = run(graph, items, args.entity_link_threshold)
        change = sum(1 for a, b in zip(baseline_preds, preds) if a != b) / len(items)
        change_rates.append(change)
        conditions.append({
            "condition": "shuffled", "seed": seed, "accuracy": acc,
            "accuracy_drop": baseline_acc - acc, "prediction_change_rate": change,
            "graph_hash": graph_hash(graph),
        })
        print(f"  {'shuffled seed=' + str(seed):22} acc={acc:.4f}  "
              f"drop={baseline_acc - acc:+.4f}  predictions changed={change:.4f}")

    stripped = strip_relations(base_graph)
    acc, preds = run(stripped, items, args.entity_link_threshold)
    change = sum(1 for a, b in zip(baseline_preds, preds) if a != b) / len(items)
    conditions.append({
        "condition": "relations_removed", "seed": None, "accuracy": acc,
        "accuracy_drop": baseline_acc - acc, "prediction_change_rate": change,
        "graph_hash": graph_hash(stripped),
    })
    print(f"  {'relations removed':22} acc={acc:.4f}  drop={baseline_acc - acc:+.4f}  "
          f"predictions changed={change:.4f}")

    mean_change = sum(change_rates) / len(change_rates)
    passed = mean_change > args.min_change_rate
    print(f"\nMean prediction change under shuffle: {mean_change:.4f}")
    print(f"Acceptance gate (> {args.min_change_rate:.2f}): {'PASS' if passed else 'FAIL'}")
    if not passed:
        print("  The pipeline's verdicts are largely recoverable without the graph's factual\n"
              "  content. Accuracy from this configuration should not be reported as verification.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "dataset": args.dataset,
            "graph": args.graph,
            "n_items": len(items),
            "entity_link_threshold": args.entity_link_threshold,
            "source_graph_hash": graph_hash(base_graph),
            "conditions": conditions,
            "mean_shuffle_prediction_change_rate": mean_change,
            "acceptance_gate": args.min_change_rate,
            "passed": passed,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
