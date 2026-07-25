"""Pair two rerun directories row-by-row and report per-cell agreement.

For datasets where the code change under test is unreachable, the resulting deltas
measure run-to-run nondeterminism of the LLM stages rather than any effect of the change.
"""

import argparse
import json
from pathlib import Path


def load(path: Path):
    """Returns (payload, rows-by-id), or (None, None) for files that carry no predictions."""
    d = json.loads(path.read_text(encoding="utf-8"))
    if "results_detail" not in d:
        return None, None
    return d, {r["id"]: r for r in d["results_detail"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    args = ap.parse_args()

    before_dir, after_dir = Path(args.before), Path(args.after)
    print(f"{'cell':34s} {'n':>4s} {'acc_before':>10s} {'acc_after':>9s} {'delta':>7s} "
          f"{'pred_flips':>10s} {'flip_%':>7s} {'crash_before':>12s}")
    print("-" * 104)

    rows_out = []
    for path in sorted(after_dir.glob("*.json")):
        if path.name in ("aggregate_summary.json", "process_manifest.json"):
            continue
        prior = before_dir / path.name
        if not prior.exists():
            continue
        d_before, rows_before = load(prior)
        d_after, rows_after = load(path)
        if rows_before is None or rows_after is None:
            continue
        shared = sorted(set(rows_before) & set(rows_after))
        if not shared:
            continue

        acc_b = sum(rows_before[i]["pred"] == rows_before[i]["gold"] for i in shared) / len(shared)
        acc_a = sum(rows_after[i]["pred"] == rows_after[i]["gold"] for i in shared) / len(shared)
        flips = sum(rows_before[i]["pred"] != rows_after[i]["pred"] for i in shared)
        crashes = sum(rows_before[i].get("raw_pred") == "Error" for i in shared)

        cell = f"{d_after['dataset']}/{d_after['model_name']}"
        print(f"{cell:34s} {len(shared):4d} {acc_b:10.4f} {acc_a:9.4f} {acc_a - acc_b:+7.4f} "
              f"{flips:10d} {flips / len(shared):7.2%} {crashes:12d}")
        rows_out.append({
            "cell": cell, "n": len(shared), "accuracy_before": acc_b, "accuracy_after": acc_a,
            "delta": acc_a - acc_b, "prediction_flips": flips,
            "flip_rate": flips / len(shared), "crashes_before": crashes,
        })

    print()
    clean = [r for r in rows_out if r["crashes_before"] == 0]
    if clean:
        deltas = [abs(r["delta"]) for r in clean]
        flips = [r["flip_rate"] for r in clean]
        print(f"Cells where the fix is unreachable (0 pre-fix crashes): {len(clean)}")
        print(f"  |delta accuracy|  max {max(deltas):.4f}  mean {sum(deltas)/len(deltas):.4f}")
        print(f"  prediction flip rate  max {max(flips):.2%}  mean {sum(flips)/len(flips):.2%}")
        print("  These are run-to-run nondeterminism, not an effect of the code change.")


if __name__ == "__main__":
    main()
