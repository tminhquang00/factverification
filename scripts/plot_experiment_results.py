"""Chart + summarize an experiment sweep's aggregate_summary.json.

Run this after every sweep (`run_benchmark_sweep.py` or similar) once its
`aggregate_summary.json` exists. It reads that file only -- it never touches
row-level `results_detail`, so it is cheap to re-run:

    python scripts/plot_experiment_results.py --dir output/experiments/<run>

With no --dir, it auto-picks the most recently modified
output/experiments/*/aggregate_summary.json.

Writes PNGs + a markdown summary to <dir>/analysis/.
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# --- palette (fixed categorical order; see dataviz skill reference) ---
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948",
)
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"
CRITICAL = "#d03b3b"
GOOD = "#0ca30c"

MODEL_COLOR = {}  # filled in per-run once we know the model set, slot 1/2 in first-seen order


def _style_ax(ax):
    ax.set_facecolor(SURFACE)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)


def find_latest_summary(base=Path("output/experiments")):
    candidates = sorted(base.glob("*/aggregate_summary.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no aggregate_summary.json under {base}/*/")
    return candidates[-1]


def load_runs(summary_path: Path):
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    runs = data["runs"]
    models = []
    for r in runs:
        if r["model"] not in models:
            models.append(r["model"])
    colors = [BLUE, ORANGE, AQUA, YELLOW]
    for m, c in zip(models, colors):
        MODEL_COLOR[m] = c
    return runs, models


def cell_label(r):
    return f"{r['dataset']}/{r['sampling']}"


def chart_accuracy_overview(runs, models, out):
    """Grouped bars: accuracy per (dataset, sampling) cell, one bar per model, 95% CI whiskers."""
    order = sorted({cell_label(r) for r in runs})
    by_cell = {}
    for r in runs:
        by_cell.setdefault(cell_label(r), {})[r["model"]] = r

    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    n_models = len(models)
    width = 0.8 / n_models
    x = range(len(order))
    for i, m in enumerate(models):
        vals, lo_err, hi_err = [], [], []
        for cell in order:
            r = by_cell[cell].get(m)
            if r is None:
                vals.append(0); lo_err.append(0); hi_err.append(0)
                continue
            acc = r["accuracy_recomputed"]
            lo, hi = r["ci95_recomputed"]
            vals.append(acc); lo_err.append(max(0, acc - lo)); hi_err.append(max(0, hi - acc))
        offs = [xi + (i - (n_models - 1) / 2) * width for xi in x]
        ax.bar(offs, vals, width=width * 0.9, color=MODEL_COLOR[m], label=m, zorder=3)
        ax.errorbar(offs, vals, yerr=[lo_err, hi_err], fmt="none", ecolor=INK_SECONDARY,
                    elinewidth=1, capsize=3, zorder=4)

    for cell_i, cell in enumerate(order):
        maj = next(iter(by_cell[cell].values()))["majority_baseline"]
        ax.hlines(maj, cell_i - 0.4, cell_i + 0.4, color=INK_MUTED, linestyle=(0, (2, 2)),
                  linewidth=1, zorder=2)

    ax.set_xticks(list(x))
    ax.set_xticklabels(order, rotation=0)
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.set_ylabel("Accuracy (95% CI)", color=INK_SECONDARY)
    fig.suptitle("Accuracy by dataset / sampling / model", color=INK, fontsize=13, x=0.01, ha="left",
                y=0.99)
    ax.set_title("dashed line = majority-class baseline for that cell", color=INK_MUTED, fontsize=8.5,
                loc="left", pad=10)
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out / "01_accuracy_overview.png", facecolor=SURFACE)
    plt.close(fig)


def chart_sampling_delta(runs, models, out):
    """Diverging bars: accuracy(random) - accuracy(prefix), per dataset x model.

    Isolates the effect of sampling order on measured accuracy -- a large negative
    delta means prefix-sampled rows were systematically easier than a random draw,
    i.e. the sweep's headline number on `prefix` is not representative of the dataset.
    """
    by_key = {(r["dataset"], r["model"], r["sampling"]): r for r in runs}
    pairs = sorted({(d, m) for d, m, s in by_key if s in ("prefix", "random")})
    labels, deltas, colors = [], [], []
    for d, m in pairs:
        pre = by_key.get((d, m, "prefix"))
        rnd = by_key.get((d, m, "random"))
        if not pre or not rnd:
            continue
        delta = rnd["accuracy_recomputed"] - pre["accuracy_recomputed"]
        labels.append(f"{d} / {m}")
        deltas.append(delta)
        colors.append(BLUE if delta >= 0 else CRITICAL)

    order = sorted(range(len(deltas)), key=lambda i: deltas[i])
    labels = [labels[i] for i in order]
    deltas = [deltas[i] for i in order]
    colors = [colors[i] for i in order]

    fig, ax = plt.subplots(figsize=(9, 0.6 * len(labels) + 1.5), dpi=150)
    y = range(len(labels))
    ax.barh(list(y), deltas, color=colors, height=0.6, zorder=3)
    ax.axvline(0, color=BASELINE, linewidth=1.2, zorder=2)
    span = max(abs(min(deltas, default=0)), abs(max(deltas, default=0)), 0.05)
    ax.set_xlim(-span * 1.35, span * 1.35)
    for yi, d in zip(y, deltas):
        if d >= 0:
            ax.text(d + span * 0.03, yi, f"{d:+.1%}", va="center", ha="left",
                    color=INK_SECONDARY, fontsize=9)
        else:
            # Label sits inside the bar near its tip so it never collides with
            # the y-axis tick labels just outside the axes to the left.
            ax.text(d + span * 0.03, yi, f"{d:+.1%}", va="center", ha="left",
                    color="white", fontsize=9, fontweight="bold")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.set_xlabel("accuracy(random sample) - accuracy(prefix sample)", color=INK_SECONDARY)
    ax.set_title("Sampling-order effect: random vs. prefix draw", color=INK, fontsize=13,
                 loc="left", pad=12)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.xaxis.grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out / "02_sampling_delta.png", facecolor=SURFACE)
    plt.close(fig)


def chart_coverage_vs_selective(runs, models, out):
    """Scatter: coverage (share of rows the pipeline actually decided) vs. selective accuracy."""
    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    for m in models:
        rs = [r for r in runs if r["model"] == m]
        xs = [r["coverage_recomputed"] for r in rs]
        ys = [r["selective_accuracy_recomputed"] for r in rs]
        ax.scatter(xs, ys, s=70, color=MODEL_COLOR[m], label=m, zorder=3,
                  edgecolors=SURFACE, linewidths=1)
        for r, x, y in zip(rs, xs, ys):
            ax.annotate(cell_label(r), (x, y), textcoords="offset points", xytext=(6, 4),
                        fontsize=7.5, color=INK_MUTED)
    ax.set_xlim(0.35, 1.02)
    ax.set_ylim(0.5, 1.02)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.set_xlabel("Coverage (rows the pipeline actually decided)", color=INK_SECONDARY)
    ax.set_ylabel("Selective accuracy (accuracy on decided rows)", color=INK_SECONDARY)
    ax.set_title("Coverage / selective-accuracy trade-off", color=INK, fontsize=13, loc="left", pad=12)
    _style_ax(ax)
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "03_coverage_vs_selective_accuracy.png", facecolor=SURFACE)
    plt.close(fig)


def chart_rmit_by_reasoning_type(runs, models, out):
    """Grouped bars: RMIT accuracy broken out by reasoning type, one bar per model."""
    rmit = [r for r in runs if r["dataset"] == "rmit"]
    if not rmit:
        return
    types = sorted({t for r in rmit for t in r["by_reasoning_type"]})
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    n_models = len(rmit)
    width = 0.8 / n_models
    x = range(len(types))
    for i, r in enumerate(rmit):
        vals = [r["by_reasoning_type"].get(t, {}).get("accuracy", 0) for t in types]
        offs = [xi + (i - (n_models - 1) / 2) * width for xi in x]
        ax.bar(offs, vals, width=width * 0.9, color=MODEL_COLOR[r["model"]], label=r["model"], zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(types, rotation=15, ha="right")
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.set_ylabel("Accuracy", color=INK_SECONDARY)
    ax.set_title("RMIT accuracy by reasoning type", color=INK, fontsize=13, loc="left", pad=12)
    _style_ax(ax)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "04_rmit_by_reasoning_type.png", facecolor=SURFACE)
    plt.close(fig)


def write_report(runs, models, out, summary_path):
    lines = []
    lines.append(f"# Experiment analysis: `{summary_path.parent.name}`\n")
    lines.append(f"Source: `{summary_path}`\n")
    lines.append(f"Models: {', '.join(models)}\n")

    lines.append("## Accuracy overview\n")
    lines.append("![accuracy overview](01_accuracy_overview.png)\n")
    lines.append("| dataset | sampling | model | n | accuracy | 95% CI | macro-F1 | majority baseline |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(runs, key=lambda r: (r["dataset"], r["sampling"], r["model"])):
        lo, hi = r["ci95_recomputed"]
        lines.append(f"| {r['dataset']} | {r['sampling']} | {r['model']} | {r['n']} | "
                     f"{r['accuracy_recomputed']:.3f} | [{lo:.3f}, {hi:.3f}] | "
                     f"{r['macro_f1']:.3f} | {r['majority_baseline']:.3f} |")

    lines.append("\n## Sampling-order effect\n")
    lines.append("![sampling delta](02_sampling_delta.png)\n")
    by_key = {(r["dataset"], r["model"], r["sampling"]): r for r in runs}
    flagged = []
    for (d, m, s), r in by_key.items():
        if s != "prefix":
            continue
        rnd = by_key.get((d, m, "random"))
        if rnd is None:
            continue
        delta = rnd["accuracy_recomputed"] - r["accuracy_recomputed"]
        if abs(delta) >= 0.10:
            flagged.append((d, m, delta))
    if flagged:
        lines.append("Cells where prefix vs. random sampling changes accuracy by >=10pp "
                     "(the prefix-sampled headline number is not representative of the dataset):\n")
        for d, m, delta in sorted(flagged, key=lambda t: t[2]):
            lines.append(f"- **{d} / {m}**: {delta:+.1%} (random vs. prefix)")
    else:
        lines.append("No cell shows a >=10pp swing between prefix and random sampling.")

    lines.append("\n## Coverage / selective accuracy\n")
    lines.append("![coverage vs selective accuracy](03_coverage_vs_selective_accuracy.png)\n")
    lines.append("Low coverage means the pipeline abstained (`Out-of-scope`/`Error`) on many rows; "
                 "selective accuracy is accuracy restricted to the rows it did decide.\n")

    if any(r["dataset"] == "rmit" for r in runs):
        lines.append("\n## RMIT by reasoning type\n")
        lines.append("![rmit by reasoning type](04_rmit_by_reasoning_type.png)\n")
        rmit = [r for r in runs if r["dataset"] == "rmit"]
        worst = []
        for r in rmit:
            for t, v in r["by_reasoning_type"].items():
                worst.append((v["accuracy"], r["model"], t))
        worst.sort()
        lines.append("Weakest (model, reasoning type) cells:\n")
        for acc, m, t in worst[:3]:
            lines.append(f"- {m} / {t}: {acc:.1%}")

    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None,
                    help="Experiment run dir containing aggregate_summary.json "
                         "(default: most recently modified under output/experiments/)")
    args = ap.parse_args()

    if args.dir:
        summary_path = Path(args.dir) / "aggregate_summary.json"
    else:
        summary_path = find_latest_summary()

    runs, models = load_runs(summary_path)
    out = summary_path.parent / "analysis"
    out.mkdir(parents=True, exist_ok=True)

    chart_accuracy_overview(runs, models, out)
    chart_sampling_delta(runs, models, out)
    chart_coverage_vs_selective(runs, models, out)
    chart_rmit_by_reasoning_type(runs, models, out)
    write_report(runs, models, out, summary_path)

    print(f"Analyzed {len(runs)} cells from {summary_path}")
    print(f"Wrote charts + README to {out}/")
    print()
    print("Reminder: run this script again after every experiment sweep --")
    print("  python scripts/plot_experiment_results.py --dir output/experiments/<new_run>")
    print("so each run gets its charts + summary alongside the raw JSON, not just the last one.")


if __name__ == "__main__":
    main()
