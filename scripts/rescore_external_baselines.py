"""Rescore saved external-baseline predictions against declaration-independent gold.

The flat-context LLM and MiniCheck runs saved their model predictions alongside a gold label that
was produced by the old declaration-coupled gold function. The predictions themselves are model
outputs and remain perfectly valid — no model needs to be called again. Only the gold column has to
be recomputed, which this script does from the reference graph and the condition graph via
:mod:`scripts.intervention_gold`.

These two baselines were always the most informative arms in the study, because the thing making
the prediction (an LLM, or a NLI-style checker) is completely independent of the thing defining
gold. Putting them on the new gold makes them directly comparable to the symbolic routing arms.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.intervention_gold import intervention_gold


def condition_graph_path(degradation_root, seed, mode, retention, filename):
    return (
        Path(degradation_root)
        / f"seed_{seed}"
        / f"{mode}__retention_{int(retention):03d}"
        / filename
    )


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize(rows, prediction_field):
    predictions = [row[prediction_field] for row in rows if row.get(prediction_field)]
    kept = [row for row in rows if row.get(prediction_field)]
    n = len(kept)
    if not n:
        return {"n_rows": 0}
    correct = sum(row[prediction_field] == row["gold"] for row in kept)
    predicted_c = [row for row in kept if row[prediction_field] == "Contradicted"]
    false_c = sum(row["gold"] != "Contradicted" for row in predicted_c)
    predicted_s = [row for row in kept if row[prediction_field] == "Supported"]
    false_s = sum(row["gold"] != "Supported" for row in predicted_s)
    true_world = [row for row in kept if row["world_truth"] == "true"]
    contradicted_true = sum(row[prediction_field] == "Contradicted" for row in true_world)
    return {
        "n_rows": n,
        "accuracy": safe_ratio(correct, n),
        "false_contradiction_rate": safe_ratio(false_c, len(predicted_c)),
        "n_predicted_contradicted": len(predicted_c),
        "false_support_rate": safe_ratio(false_s, len(predicted_s)),
        "n_predicted_supported": len(predicted_s),
        "contradiction_rate_on_true_claims": safe_ratio(contradicted_true, len(true_world)),
        "n_true_world_claims": len(true_world),
        "n_contradicted_true_world_claims": contradicted_true,
        "decision_coverage": safe_ratio(
            sum(row[prediction_field] != "Not-in-KG" for row in kept), n
        ),
        "gold_distribution": dict(Counter(row["gold"] for row in kept)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--full_graph", default="data/nusmods_graph.json")
    parser.add_argument("--degradation_dir", default="output/experiments/nusmods_degradation_final")
    parser.add_argument("--degraded_graph_filename", default="nusmods_graph.json")
    parser.add_argument("--prediction_fields", nargs="+", default=["prediction", "binary_prediction"])
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = payload["rows"]
    full_graph = json.loads(Path(args.full_graph).read_text(encoding="utf-8"))

    graph_cache = {}
    changed = 0
    anomalies = Counter()
    for row in rows:
        key = (row["seed"], row["mode"], row["retention"])
        if key not in graph_cache:
            path = condition_graph_path(
                args.degradation_dir, row["seed"], row["mode"], row["retention"],
                args.degraded_graph_filename,
            )
            graph_cache[key] = json.loads(path.read_text(encoding="utf-8"))
        gold_record = intervention_gold(tuple(row["triple"]), full_graph, graph_cache[key])
        if gold_record["anomaly"]:
            anomalies[gold_record["anomaly"]] += 1
        row["gold_previous_declaration_coupled"] = row.get("gold")
        if row.get("gold") != gold_record["verdict"]:
            changed += 1
        row["gold"] = gold_record["verdict"]
        row["world_truth"] = gold_record["world_truth"]
        row["evidence_state"] = gold_record["evidence_state"]
        row["gold_anomaly"] = gold_record["anomaly"]

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["mode"], row["retention"])].append(row)

    summaries = {}
    for field in args.prediction_fields:
        if not any(field in row for row in rows):
            continue
        summaries[field] = {
            f"{mode}__{retention}": summarize(group, field)
            for (mode, retention), group in sorted(grouped.items(), key=lambda i: (i[0][0], -i[0][1]))
        }
        summaries[field]["overall"] = summarize(rows, field)

    output = {
        "source": args.input,
        "run": payload.get("run"),
        "gold_definition": {
            "module": "scripts/intervention_gold.py",
            "reads_completeness_declaration": False,
            "rows_whose_gold_changed": changed,
            "rows_total": len(rows),
            "gold_anomalies": dict(anomalies),
        },
        "summaries": summaries,
        "rows": rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"gold changed on {changed}/{len(rows)} rows; anomalies={dict(anomalies) or 'none'}")
    print(json.dumps(summaries, indent=2)[:2000])
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
