"""Recompute aggregate metrics for a rerun directory directly from row-level predictions.

Every number this script emits is derived from `results_detail` rows, not from the
aggregate fields written by the evaluation harnesses. Where a recomputed value
disagrees with the stored value, both are reported.
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

CLASSES = ["Supported", "Contradicted", "Not-in-KG"]
# Raw pipeline outcomes that are not one of the three decision classes.
NON_DECISION = ["Out-of-scope", "Error"]


def bootstrap_ci(rows, resamples=1000, seed=20260725, level=0.95):
    """IID bootstrap over rows. Matches the harness estimator (rows, not clusters)."""
    n = len(rows)
    if n == 0:
        return 0.0, 0.0
    correct = [1 if r["pred"] == r["gold"] else 0 for r in rows]
    rng = random.Random(seed)
    accs = []
    for _ in range(resamples):
        accs.append(sum(correct[rng.randrange(n)] for _ in range(n)) / n)
    accs.sort()
    return accs[int((1 - level) / 2 * resamples)], accs[int((1 + level) / 2 * resamples)]


# NOTE: no clustered interval is reported here. These row records carry no subject
# entity field, and the only available grouping key (the id prefix) encodes the gold
# label rather than an entity, so resampling it would produce a meaningless interval.
# A subject-clustered CI requires re-emitting rows with an explicit subject id.


def per_class(rows):
    stats = {c: {"tp": 0, "fp": 0, "fn": 0} for c in CLASSES}
    for r in rows:
        p, g = r["pred"], r["gold"]
        if p == g:
            if p in stats:
                stats[p]["tp"] += 1
        else:
            if p in stats:
                stats[p]["fp"] += 1
            if g in stats:
                stats[g]["fn"] += 1
    out = {}
    for c in CLASSES:
        tp, fp, fn = stats[c]["tp"], stats[c]["fp"], stats[c]["fn"]
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[c] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return out


def summarize(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = d["results_detail"]
    n = len(rows)
    gold = Counter(r["gold"] for r in rows)
    pred = Counter(r["pred"] for r in rows)
    raw = Counter(r.get("raw_pred", r["pred"]) for r in rows)

    acc = sum(1 for r in rows if r["pred"] == r["gold"]) / n
    lo, hi = bootstrap_ci(rows)
    pc = per_class(rows)
    present = [c for c in CLASSES if pc[c]["support"] > 0]
    macro_f1 = sum(pc[c]["f1"] for c in present) / len(present) if present else 0.0

    # Chance floors
    majority_label, majority_count = gold.most_common(1)[0]

    # Harness failures: rows where the pipeline raised and the harness substituted a
    # default label. These are scored as predictions, which biases accuracy toward
    # whichever class the harness defaults to.
    n_error = raw.get("Error", 0)
    err_rows = [r for r in rows if r.get("raw_pred") == "Error"]
    err_credited = sum(1 for r in err_rows if r["pred"] == r["gold"])

    # Coverage = share of rows where the pipeline returned an actual decision.
    covered = [r for r in rows if r.get("raw_pred", r["pred"]) in ("Supported", "Contradicted", "Not-in-KG")]
    if d["dataset"] == "factkg":
        # FactKG is forced-binary: Not-in-KG is collapsed into Contradicted, so only
        # Supported/Contradicted count as covered (this matches the harness).
        covered = [r for r in rows if r.get("raw_pred") in ("Supported", "Contradicted")]
    cov = len(covered) / n if n else 0.0
    sel_acc = (sum(1 for r in covered if r["pred"] == r["gold"]) / len(covered)) if covered else 0.0

    # Accuracy over rows the pipeline actually completed (errors excluded entirely).
    ok_rows = [r for r in rows if r.get("raw_pred") != "Error"]
    acc_excl_err = (sum(1 for r in ok_rows if r["pred"] == r["gold"]) / len(ok_rows)) if ok_rows else 0.0

    by_reasoning = {}
    for rt in sorted({r.get("reasoning_type", "N/A") for r in rows}):
        sub = [r for r in rows if r.get("reasoning_type", "N/A") == rt]
        by_reasoning[rt] = {
            "n": len(sub),
            "accuracy": sum(1 for r in sub if r["pred"] == r["gold"]) / len(sub),
            "errors": sum(1 for r in sub if r.get("raw_pred") == "Error"),
        }

    confusion = Counter((r["gold"], r["pred"]) for r in rows)

    return {
        "file": path.name,
        "dataset": d["dataset"],
        "model": d["model_name"],
        "provider": d["provider"],
        "n": n,
        "accuracy_recomputed": acc,
        "accuracy_stored": d.get("accuracy"),
        "ci95_recomputed": [lo, hi],
        "ci95_stored": d.get("ci_95"),
        "macro_f1": macro_f1,
        "per_class": pc,
        "gold_dist": dict(gold),
        "pred_dist": dict(pred),
        "raw_pred_dist": dict(raw),
        "majority_label": majority_label,
        "majority_baseline": majority_count / n,
        "harness_errors": n_error,
        "harness_error_rate": n_error / n if n else 0.0,
        "errors_scored_correct": err_credited,
        "accuracy_excluding_errors": acc_excl_err,
        "n_excluding_errors": len(ok_rows),
        "coverage_recomputed": cov,
        "coverage_stored": d.get("coverage"),
        "selective_accuracy_recomputed": sel_acc,
        "selective_accuracy_stored": d.get("selective_accuracy"),
        "by_reasoning_type": by_reasoning,
        "confusion": {f"{g}->{p}": c for (g, p), c in sorted(confusion.items())},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="output/experiments/rerun_20260725")
    ap.add_argument("--out", default=None, help="Write the aggregate JSON here.")
    args = ap.parse_args()

    directory = Path(args.dir)
    results = []
    for path in sorted(directory.glob("*.json")):
        if path.name in ("process_manifest.json",) or path.name.endswith(".summary.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[skip] {path.name}: not valid JSON (run may be incomplete)")
            continue
        if "results_detail" not in data:
            continue
        results.append(summarize(path))

    for r in results:
        print("=" * 78)
        print(f"{r['dataset']:8s} | {r['model']:16s} | n={r['n']}")
        print(f"  accuracy        {r['accuracy_recomputed']:.4f}  (stored {r['accuracy_stored']})")
        print(f"  iid 95% CI      [{r['ci95_recomputed'][0]:.4f}, {r['ci95_recomputed'][1]:.4f}]"
              f"   stored {r['ci95_stored']}")
        print(f"  macro-F1        {r['macro_f1']:.4f}")
        print(f"  majority base   {r['majority_baseline']:.4f} ({r['majority_label']})")
        print(f"  coverage        {r['coverage_recomputed']:.4f}   sel.acc {r['selective_accuracy_recomputed']:.4f}")
        print(f"  harness errors  {r['harness_errors']} ({r['harness_error_rate']:.2%}), "
              f"{r['errors_scored_correct']} of them scored CORRECT by default label")
        print(f"  acc excl errors {r['accuracy_excluding_errors']:.4f} (n={r['n_excluding_errors']})")
        print(f"  gold {r['gold_dist']}")
        print(f"  pred {r['pred_dist']}")
        print(f"  raw  {r['raw_pred_dist']}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"runs": results}, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
