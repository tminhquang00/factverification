"""Recompute every NUSMods aggregate from row-level predictions and test the ablation arms.

Nothing here reads a stored `accuracy` field. Each number is recomputed from `results_detail`,
per the registry's row-level requirement, and any disagreement with the stored value is reported.

Arms that share a sample seed are scored on identical rows, so the comparison against the
reference arm is **paired**. Paired arms are tested with an exact McNemar test on the discordant
pairs rather than by comparing two independent confidence intervals, which is the wrong test:
overlapping CIs on paired data do not imply the difference is inside the noise floor, and
disjoint CIs overstate the evidence.

Usage
-----
    & .venv\\Scripts\\python.exe -m scripts.analyze_nusmods_results `
        --dir output\\experiments\\nusmods_20260726 `
        --out output\\experiments\\nusmods_20260726\\analysis_summary.json
"""

import argparse
import collections
import json
import math
import random
from pathlib import Path

CLASSES = ["Supported", "Contradicted", "Not-in-KG"]
REFERENCE = "nusmods__gemma_4_e4b__pipeline"


def load(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "results_detail" not in payload:
        return None
    payload["_rows"] = {row["id"]: row for row in payload["results_detail"]}
    payload["_name"] = path.stem
    return payload


def bootstrap_ci(rows, n_boot=2000, seed=7):
    """Percentile bootstrap over scored rows, under a fixed seed so the interval is reproducible."""
    scored = [r for r in rows if r["pred"] is not None]
    if not scored:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(scored)
    accuracies = []
    for _ in range(n_boot):
        hits = sum(1 for _ in range(n)
                   if (lambda r: r["pred"] == r["gold"])(scored[rng.randrange(n)]))
        accuracies.append(hits / n)
    accuracies.sort()
    return accuracies[int(0.025 * n_boot)], accuracies[int(0.975 * n_boot)]


def metrics(payload):
    rows = payload["results_detail"]
    scored = [r for r in rows if r["pred"] is not None]
    correct = sum(1 for r in scored if r["pred"] == r["gold"])
    accuracy = correct / len(scored) if scored else 0.0

    per_class, f1s = {}, []
    for cls in CLASSES:
        tp = sum(1 for r in scored if r["pred"] == cls and r["gold"] == cls)
        fp = sum(1 for r in scored if r["pred"] == cls and r["gold"] != cls)
        fn = sum(1 for r in scored if r["pred"] != cls and r["gold"] == cls)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[cls] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
        f1s.append(f1)

    gold_dist = collections.Counter(r["gold"] for r in rows)
    raw_dist = collections.Counter(r.get("raw_pred") for r in rows)
    decisive = [r for r in rows if r.get("raw_pred") in CLASSES]
    lower, upper = bootstrap_ci(rows)

    return {
        "name": payload["_name"],
        "dataset": payload["dataset"],
        "method": payload["method"],
        "model": payload["model_name"],
        "provider": payload["provider"],
        "entity_link_threshold": payload.get("entity_link_threshold"),
        "routing_mode": payload.get("routing_mode") or "dynamic",
        "sample_seed": payload.get("sample_seed"),
        "n_total": len(rows),
        "n_scored": len(scored),
        "n_unscored": len(rows) - len(scored),
        "accuracy": accuracy,
        "accuracy_stored": payload.get("accuracy"),
        "accuracy_matches_stored": abs(accuracy - (payload.get("accuracy") or 0)) < 1e-9,
        "ci95": [lower, upper],
        "macro_f1": sum(f1s) / len(f1s),
        "majority_floor": max(gold_dist.values()) / len(rows),
        "per_class": per_class,
        "coverage": len(decisive) / len(rows) if rows else 0.0,
        "selective_accuracy": (sum(1 for r in decisive if r["raw_pred"] == r["gold"]) / len(decisive)
                               if decisive else 0.0),
        "raw_verdict_distribution": dict(raw_dist),
        "by_reasoning_type": {
            rtype: {
                "n": len([r for r in scored if r["reasoning_type"] == rtype]),
                "accuracy": (sum(1 for r in scored
                                 if r["reasoning_type"] == rtype and r["pred"] == r["gold"])
                             / max(1, len([r for r in scored if r["reasoning_type"] == rtype]))),
            }
            for rtype in sorted({r["reasoning_type"] for r in rows})
        },
        "confusion": dict(collections.Counter(
            f"{r['gold']}->{r['pred']}" for r in scored)),
        "usage": {
            "calls_per_row": payload["usage"]["per_row"]["calls_per_row"],
            "tokens_per_row": payload["usage"]["per_row"]["tokens_per_row"],
            "total_tokens": payload["usage"]["total_tokens"],
            "latency_mean_s": payload["usage"]["latency_s"]["mean"],
            "latency_p95_s": payload["usage"]["latency_s"]["p95"],
        },
    }


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value over the b + c discordant pairs.

    Under H0 each discordant pair is a fair coin, so the count follows Binomial(b + c, 0.5).
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def pair(reference, arm):
    """Paired comparison on the rows both arms scored."""
    shared = sorted(set(reference["_rows"]) & set(arm["_rows"]))
    shared = [i for i in shared
              if reference["_rows"][i]["pred"] is not None and arm["_rows"][i]["pred"] is not None]
    if not shared:
        return None

    def hit(payload, row_id):
        row = payload["_rows"][row_id]
        return row["pred"] == row["gold"]

    b = sum(1 for i in shared if hit(reference, i) and not hit(arm, i))
    c = sum(1 for i in shared if not hit(reference, i) and hit(arm, i))
    flips = sum(1 for i in shared
                if reference["_rows"][i]["pred"] != arm["_rows"][i]["pred"])
    acc_ref = sum(1 for i in shared if hit(reference, i)) / len(shared)
    acc_arm = sum(1 for i in shared if hit(arm, i)) / len(shared)
    return {
        "arm": arm["_name"],
        "reference": reference["_name"],
        "n_paired": len(shared),
        "same_sample_seed": reference.get("sample_seed") == arm.get("sample_seed"),
        "accuracy_reference": acc_ref,
        "accuracy_arm": acc_arm,
        "delta": acc_arm - acc_ref,
        "reference_only_correct": b,
        "arm_only_correct": c,
        "prediction_flip_rate": flips / len(shared),
        "mcnemar_p": mcnemar_exact(b, c),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default="output/experiments/nusmods_20260726")
    parser.add_argument("--reference", default=REFERENCE)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    root = Path(args.dir)
    paths = sorted(root.glob("*.json")) + sorted((root / "ablation").glob("*.json"))
    payloads = [p for p in (load(path) for path in paths) if p]
    if not payloads:
        raise SystemExit(f"No result files with row-level predictions under {root}")

    summaries = [metrics(p) for p in payloads]
    by_name = {p["_name"]: p for p in payloads}

    print(f"{'cell':52s} {'n':>4s} {'acc':>7s} {'ci95':>16s} {'macroF1':>8s} "
          f"{'cov':>6s} {'selacc':>7s} {'uns':>4s} {'tok/row':>8s}")
    print("-" * 124)
    for summary in summaries:
        print(f"{summary['name'][:52]:52s} {summary['n_scored']:4d} {summary['accuracy']:7.4f} "
              f"[{summary['ci95'][0]:.3f},{summary['ci95'][1]:.3f}] {summary['macro_f1']:8.4f} "
              f"{summary['coverage']:6.3f} {summary['selective_accuracy']:7.4f} "
              f"{summary['n_unscored']:4d} {summary['usage']['tokens_per_row']:8.1f}")
        if not summary["accuracy_matches_stored"]:
            print(f"    ! recomputed accuracy disagrees with the stored value "
                  f"({summary['accuracy']:.4f} vs {summary['accuracy_stored']})")

    comparisons = []
    reference = by_name.get(args.reference)
    if reference:
        print(f"\nPaired comparisons against {args.reference}")
        print(f"{'arm':52s} {'n':>4s} {'delta':>8s} {'ref+':>5s} {'arm+':>5s} "
              f"{'flip%':>7s} {'McNemar p':>10s}")
        print("-" * 100)
        for payload in payloads:
            if payload["_name"] == args.reference:
                continue
            result = pair(reference, payload)
            if not result:
                continue
            comparisons.append(result)
            print(f"{result['arm'][:52]:52s} {result['n_paired']:4d} {result['delta']:+8.4f} "
                  f"{result['reference_only_correct']:5d} {result['arm_only_correct']:5d} "
                  f"{result['prediction_flip_rate']:7.2%} {result['mcnemar_p']:10.4g}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"cells": summaries, "paired_comparisons": comparisons},
                                  indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
