"""Analyse the multi-vendor tri-state verifier panel.

The question this answers
-------------------------
The two-model study showed a tri-state prompt reduces false contradictions unequally across models.
This script tests which of three explanations the panel supports:

1. **Capability scaling** — stronger models abstain correctly, so the problem solves itself.
   Signature: contradiction rate on true claims falls monotonically with model strength, and the
   strongest models approach zero.
2. **Idiosyncrasy** — abstention is a training-recipe quirk, uncorrelated with capability.
   Signature: wide spread within a capability tier, and vendor explaining more variance than tier.
3. **A structural floor** — every model retains substantial harm under severe incompleteness.
   Signature: even the best model stays far above zero at 20% retention.

These are distinguishable, and the answer determines whether explicit completeness metadata is a
temporary workaround or a permanent requirement.

Metrics
-------
``contradiction_rate_on_true_claims`` is the headline. Of the claims true in the reference world,
what fraction did the model call ``Contradicted``? It needs no convention about how absence should
be labelled, so it is comparable across models and robust to disagreement with our gold design.

``abstention_benefit`` is the ratio of the binary-collapse rate to the tri-state rate at a given
retention. It isolates how much a model gains from *being allowed* to say "unknown", separating that
from raw accuracy. A ratio of 1.0 means the third label bought the model nothing.

``competence_at_full_retention`` is tri-state accuracy on the intact graph. Regressing the 20%
harm against it is the direct test of the capability-scaling hypothesis.
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.run_model_panel import MODEL_METADATA  # noqa: E402


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def cluster_bootstrap(rows, numerator_fn, denominator_fn, iterations, seed):
    """Question-clustered bootstrap interval for a ratio of two row counts."""
    clusters = defaultdict(lambda: [0, 0])
    for row in rows:
        bucket = clusters[row["question_id"]]
        bucket[0] += numerator_fn(row)
        bucket[1] += denominator_fn(row)
    if not clusters:
        return None
    totals = np.array(list(clusters.values()), dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(totals), size=(iterations, len(totals)))
    sampled = totals[indices].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratios = np.where(sampled[:, 1] > 0, sampled[:, 0] / sampled[:, 1], np.nan)
    finite = ratios[np.isfinite(ratios)]
    if not len(finite):
        return None
    low, high = np.percentile(finite, [2.5, 97.5])
    return [float(low), float(high)]


def summarize_cell(rows, prediction_field, iterations, seed):
    scored = [row for row in rows if row.get(prediction_field)]
    if not scored:
        return {"n_rows": 0}
    true_world = [row for row in scored if row.get("world_truth") == "true"]
    contradicted_true = sum(row[prediction_field] == "Contradicted" for row in true_world)
    predicted_c = [row for row in scored if row[prediction_field] == "Contradicted"]
    predicted_s = [row for row in scored if row[prediction_field] == "Supported"]

    # Abstention *quality*, which separates a well-calibrated model from one that just says
    # "unknown" to everything. A model can drive contradiction_rate_on_true_claims to zero by
    # abstaining always, so that metric must always be read next to these two.
    gold_unknown = [row for row in scored if row["gold"] == "Not-in-KG"]
    abstained = [row for row in scored if row[prediction_field] == "Not-in-KG"]
    abstention_recall = safe_ratio(
        sum(row[prediction_field] == "Not-in-KG" for row in gold_unknown), len(gold_unknown)
    )
    abstention_precision = safe_ratio(
        sum(row["gold"] == "Not-in-KG" for row in abstained), len(abstained)
    )
    return {
        # Of the claims the graph genuinely cannot settle, how many did the model abstain on?
        "abstention_recall": abstention_recall,
        # Of the model's abstentions, how many were warranted? Low means indiscriminate abstention.
        "abstention_precision": abstention_precision,
        "n_rows": len(scored),
        "accuracy": safe_ratio(sum(row[prediction_field] == row["gold"] for row in scored), len(scored)),
        "contradiction_rate_on_true_claims": safe_ratio(contradicted_true, len(true_world)),
        "contradiction_rate_on_true_claims_ci95": cluster_bootstrap(
            scored,
            lambda r: int(r.get("world_truth") == "true" and r[prediction_field] == "Contradicted"),
            lambda r: int(r.get("world_truth") == "true"),
            iterations, seed,
        ),
        "n_true_world_claims": len(true_world),
        "n_contradicted_true_world_claims": contradicted_true,
        "false_contradiction_rate": safe_ratio(
            sum(row["gold"] != "Contradicted" for row in predicted_c), len(predicted_c)
        ),
        "false_support_rate": safe_ratio(
            sum(row["gold"] != "Supported" for row in predicted_s), len(predicted_s)
        ),
        "abstention_rate": safe_ratio(
            sum(row[prediction_field] == "Not-in-KG" for row in scored), len(scored)
        ),
        "decision_coverage": safe_ratio(
            sum(row[prediction_field] != "Not-in-KG" for row in scored), len(scored)
        ),
    }


def spearman(xs, ys):
    """Rank correlation without a SciPy dependency; returns None when undefined."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = shared
            i = j + 1
        return ranks

    rx = rank([p[0] for p in pairs])
    ry = rank([p[1] for p in pairs])
    if len(set(rx)) < 2 or len(set(ry)) < 2:
        return None
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel_dir", default="output/experiments/model_panel_20260803")
    parser.add_argument("--output", default="output/experiments/model_panel_20260803/panel_analysis.json")
    parser.add_argument("--headline_retention", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()

    panel_dir = Path(args.panel_dir)
    manifest_path = panel_dir / "panel_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    # Prefer the manifest (it records what the panel actually ran) but fall back to the static table
    # so partial panels can be inspected before the manifest is written.
    metadata = dict(MODEL_METADATA)
    metadata.update({
        r["model"]: r["metadata"] for r in manifest.get("results", []) if r.get("metadata")
    })

    per_model = {}
    sampling_notes = {}
    for path in sorted(panel_dir.glob("flat_*.json")):
        if path.name.endswith(".checkpoint.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = payload["run"]["model"]
        sampling_notes[model] = payload["run"].get("sampling", {})
        rows = payload["rows"]
        by_retention = defaultdict(list)
        for row in rows:
            if row["mode"] != "random":
                continue
            by_retention[row["retention"]].append(row)

        cells = {}
        for retention, group in sorted(by_retention.items(), reverse=True):
            cells[str(retention)] = {
                "tristate": summarize_cell(group, "prediction", args.iterations, args.seed + retention),
                "binary_collapse": summarize_cell(
                    group, "binary_prediction", args.iterations, args.seed + retention
                ),
            }

        headline = cells.get(str(args.headline_retention), {})
        tri = headline.get("tristate", {}).get("contradiction_rate_on_true_claims")
        binary = headline.get("binary_collapse", {}).get("contradiction_rate_on_true_claims")
        full = cells.get("100", {}).get("tristate", {})
        per_model[model] = {
            "metadata": metadata.get(model, {}),
            "sampling": sampling_notes[model],
            "n_prediction_failures": sum(1 for row in rows if row.get("error")),
            "by_retention": cells,
            "headline": {
                "retention": args.headline_retention,
                "tristate_contradiction_rate_on_true_claims": tri,
                "binary_contradiction_rate_on_true_claims": binary,
                "abstention_benefit": (binary / tri) if tri else None,
                "competence_at_full_retention": full.get("accuracy"),
                "abstention_rate": headline.get("tristate", {}).get("abstention_rate"),
            },
        }

    models = sorted(per_model)
    harm = [per_model[m]["headline"]["tristate_contradiction_rate_on_true_claims"] for m in models]
    competence = [per_model[m]["headline"]["competence_at_full_retention"] for m in models]
    benefit = [per_model[m]["headline"]["abstention_benefit"] for m in models]
    finite_harm = [h for h in harm if h is not None]

    by_vendor = defaultdict(list)
    by_tier = defaultdict(list)
    for model in models:
        value = per_model[model]["headline"]["tristate_contradiction_rate_on_true_claims"]
        if value is None:
            continue
        by_vendor[per_model[model]["metadata"].get("vendor", "unknown")].append(value)
        by_tier[per_model[model]["metadata"].get("tier", "unknown")].append(value)

    def group_stats(groups):
        return {
            name: {
                "n_models": len(values),
                "mean": statistics.fmean(values),
                "min": min(values),
                "max": max(values),
            }
            for name, values in sorted(groups.items())
        }

    hypothesis = {
        "spearman_competence_vs_harm": spearman(competence, harm),
        "spearman_competence_vs_abstention_benefit": spearman(competence, benefit),
        "harm_spread": {
            "n_models": len(finite_harm),
            "min": min(finite_harm) if finite_harm else None,
            "max": max(finite_harm) if finite_harm else None,
            "mean": statistics.fmean(finite_harm) if finite_harm else None,
            "median": statistics.median(finite_harm) if finite_harm else None,
            "best_model": min(models, key=lambda m: (
                harm[models.index(m)] if harm[models.index(m)] is not None else 1e9
            )) if finite_harm else None,
        },
        "reading_guide": {
            "capability_scaling": (
                "Supported when spearman_competence_vs_harm is strongly negative AND the best "
                "model's harm approaches zero."
            ),
            "idiosyncrasy": (
                "Supported when the within-tier spread is comparable to the across-tier spread, "
                "i.e. tier explains little."
            ),
            "structural_floor": (
                "Supported when even the minimum harm across the whole panel stays well above zero."
            ),
        },
    }

    output = {
        "protocol": manifest.get("protocol", {}),
        "headline_retention": args.headline_retention,
        "metric_note": (
            "contradiction_rate_on_true_claims is the fraction of reference-world-true claims the "
            "model called Contradicted. It requires no convention about how absence should be "
            "labelled, so it is comparable across models."
        ),
        "sampling_confound": {
            "note": (
                "Models that reject temperature=0 run at a provider default. Part of any difference "
                "between them and a temperature-0 model is sampling, not capability."
            ),
            "models_not_honouring_requested_temperature": sorted(
                model for model, info in sampling_notes.items()
                if info and not info.get("temperature_honoured", True)
            ),
        },
        "hypothesis_tests": hypothesis,
        "by_vendor": group_stats(by_vendor),
        "by_tier": group_stats(by_tier),
        "per_model": per_model,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(f"{'model':<24} {'vendor':<11} {'tier':<13} {'acc@100':>8} {'CRtrue@20':>10} {'binary@20':>10} {'benefit':>8}")
    for model in models:
        h = per_model[model]["headline"]
        m = per_model[model]["metadata"]

        def fmt(value, pct=True):
            if value is None:
                return "     n/a"
            return f"{value*100:7.1f}%" if pct else f"{value:7.2f}x"

        print(f"{model:<24} {m.get('vendor','?'):<11} {m.get('tier','?'):<13} "
              f"{fmt(h['competence_at_full_retention'])} "
              f"{fmt(h['tristate_contradiction_rate_on_true_claims'])} "
              f"{fmt(h['binary_contradiction_rate_on_true_claims'])} "
              f"{fmt(h['abstention_benefit'], pct=False)}")
    print()
    print(json.dumps(hypothesis["harm_spread"], indent=2))
    print("spearman(competence, harm) =", hypothesis["spearman_competence_vs_harm"])
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
