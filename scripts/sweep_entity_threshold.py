"""Select the stage-3 entity-link rejection threshold on a held-out split.

`link_entity` accepts a bi-encoder cosine match at 0.35 by default, so a subject the graph
does not contain is linked to its nearest neighbour instead of being reported unresolved.
On CoDEx this costs the `Not-in-KG` class most of its recall: all 97 genuinely-absent
subjects in the first 500 rows were linked to some wrong entity.

The threshold is a hyperparameter, so it is selected on a DEVELOPMENT split and reported on a
disjoint TEST split. Selecting it on the evaluation rows would be tuning on the test set.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\sweep_entity_threshold.py
    & .venv\\Scripts\\python.exe scripts\\sweep_entity_threshold.py --out output/diagnostics/threshold_sweep.json
"""

import argparse
import json
from pathlib import Path

from scripts.diagnose_object_namespace import TEMPLATES, _NoLLM, evaluate  # noqa: F401
from verification_pipeline import VerificationPipeline


def load_split(path: Path, start: int, end: int):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[start:end]
    items = []
    for row in rows:
        triples = row.get("triples") or []
        if not triples:
            continue
        subject, relation = str(triples[0][0]), str(triples[0][1])
        for template in TEMPLATES:
            match = template.match(row["text"])
            if match:
                items.append((row["gold_label"], subject, relation, match.group("obj")))
                break
    return items


def accuracy(pipeline, items):
    predictions = evaluate(pipeline, items)
    return sum(1 for (gold, *_), pred in zip(items, predictions) if gold == pred) / len(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="data/codex_test.jsonl")
    parser.add_argument("--graph", default="data/codex_graph.json")
    parser.add_argument("--test_range", type=int, nargs=2, default=[0, 500])
    parser.add_argument("--dev_range", type=int, nargs=2, default=[500, 1000])
    parser.add_argument("--thresholds", type=float, nargs="+",
                        default=[0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    path = Path(args.dataset)
    dev = load_split(path, *args.dev_range)
    test = load_split(path, *args.test_range)
    print(f"DEV rows {args.dev_range} n={len(dev)}   TEST rows {args.test_range} n={len(test)}\n")
    print(f"{'threshold':>10}{'DEV acc':>10}{'TEST acc':>10}")

    rows, best = [], (-1.0, None)
    for threshold in args.thresholds:
        pipeline = VerificationPipeline(
            kg_path=args.graph, llm_client=_NoLLM(), entity_link_threshold=threshold
        )
        dev_acc, test_acc = accuracy(pipeline, dev), accuracy(pipeline, test)
        rows.append({"threshold": threshold, "dev_accuracy": dev_acc, "test_accuracy": test_acc})
        if dev_acc > best[0]:
            best = (dev_acc, threshold)
        print(f"{threshold:>10.2f}{dev_acc:>10.4f}{test_acc:>10.4f}")

    selected = best[1]
    selected_test = next(r["test_accuracy"] for r in rows if r["threshold"] == selected)
    print(f"\nDEV-selected threshold {selected} -> TEST accuracy {selected_test:.4f}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "dataset": args.dataset,
            "dev_range": args.dev_range,
            "test_range": args.test_range,
            "sweep": rows,
            "dev_selected_threshold": selected,
            "test_accuracy_at_selected": selected_test,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
