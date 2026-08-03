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

    & .venv\\Scripts\\python.exe -m scripts.run_kg_destruction_control `
        --benchmark nusmods --entity_link_threshold 0.95 `
        --out output\\diagnostics\\nusmods_destruction_control.json
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

# Fields that carry graph scaffolding rather than facts, per benchmark. Everything NOT listed
# here is destroyed by the control, so the set decides what the gate actually tests. CoDEx's
# facts live in open-domain relation keys and `credits`/`school`/`prerequisites` are unused
# scaffolding; on NUSMods those three fields ARE the facts under test, so they must be
# destroyable or the control would shuffle nothing and pass vacuously.
SCAFFOLDING = {
    "codex": {
        "course_id", "title", "prerequisites", "credits", "school",
        "coordinator", "coordinator_email", "description",
    },
    "nusmods": {
        "course_id", "title", "academic_year", "description",
        "prerequisite_text", "preclusion_text",
    },
}
RESERVED = SCAFFOLDING["codex"]


def load_nusmods_items(path: Path, limit: int):
    """Loads (gold, subject, relation, asserted_object) tuples from `asserted_triples`.

    Multi-triple rows are flattened to their first triple so one row yields one prediction, which
    keeps the change-rate denominator equal to the row count.
    """
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    items, unparsed = [], 0
    for row in rows[:limit]:
        asserted = row.get("asserted_triples") or []
        if not asserted:
            unparsed += 1
            continue
        subject, relation, obj = asserted[0]
        items.append((row["gold_label"], str(subject), str(relation), str(obj)))
    return items, unparsed


LOADERS = {"codex": load_asserted_items, "nusmods": load_nusmods_items}
DEFAULT_PATHS = {
    "codex": ("data/codex_test.jsonl", "data/codex_graph.json"),
    "nusmods": ("data/nusmods_test.jsonl", "data/nusmods_graph.json"),
}


def graph_hash(graph) -> str:
    payload = json.dumps(graph, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def shuffle_within_relation(graph, seed, reserved=RESERVED):
    """Permutes each relation's values across entities, preserving the value multiset."""
    out = copy.deepcopy(graph)
    rng = random.Random(seed)
    by_relation = collections.defaultdict(list)
    for key, record in out.items():
        for field in record:
            if field not in reserved:
                by_relation[field].append(key)
    for field, keys in by_relation.items():
        values = [out[key][field] for key in keys]
        rng.shuffle(values)
        for key, value in zip(keys, values):
            out[key][field] = value
    return out


def strip_relations(graph, reserved=RESERVED):
    """Removes every open-domain relation, leaving the entity scaffolding intact."""
    out = copy.deepcopy(graph)
    for record in out.values():
        for field in [f for f in record if f not in reserved]:
            del record[field]
    return out


def run(graph, items, threshold):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "graph.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(graph, handle)
        pipeline = VerificationPipeline(
            kg_path=path, llm_client=_NoLLM(), entity_link_threshold=threshold,
            # Control items supply canonical entity IDs. Dense retrieval cannot change the
            # mapping, and rebuilding a 30k-key embedding matrix for every shuffle dominates the
            # runtime without changing a prediction.
            enable_dense_linking=False,
            routing_mode="occupancy",
        )
        predictions = evaluate(pipeline, items)
    golds = [g for g, _, _, _ in items]
    accuracy = sum(1 for g, p in zip(golds, predictions) if g == p) / len(items)
    return accuracy, predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--benchmark", default="codex", choices=sorted(LOADERS),
                        help="Selects the item loader and the scaffolding field set.")
    parser.add_argument("--dataset", default=None, help="Defaults to the benchmark's test file.")
    parser.add_argument("--graph", default=None, help="Defaults to the benchmark's graph.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 23, 37, 53, 71])
    parser.add_argument("--entity_link_threshold", type=float, default=0.95)
    parser.add_argument("--min_change_rate", type=float, default=0.20,
                        help="Acceptance gate: prediction change rate under shuffle must exceed this.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    default_dataset, default_graph = DEFAULT_PATHS[args.benchmark]
    args.dataset = args.dataset or default_dataset
    args.graph = args.graph or default_graph
    reserved = SCAFFOLDING[args.benchmark]

    items, unparsed = LOADERS[args.benchmark](Path(args.dataset), args.limit)
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
        graph = shuffle_within_relation(base_graph, seed, reserved)
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

    stripped = strip_relations(base_graph, reserved)
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
            "benchmark": args.benchmark,
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
