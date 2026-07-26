"""Figures for the NUSMods study.

Reads the recomputed aggregates written by `scripts/analyze_nusmods_results.py` plus the two
LLM-free diagnostics, and writes the paper's figures to <dir>/analysis/.

    & .venv\\Scripts\\python.exe -m scripts.analyze_nusmods_results --dir output\\experiments\\nusmods_20260726 `
        --out output\\experiments\\nusmods_20260726\\analysis_summary.json
    & .venv\\Scripts\\python.exe -m scripts.plot_nusmods_results --dir output\\experiments\\nusmods_20260726

Palette and axis treatment match `scripts/plot_experiment_results.py` so the NUSMods figures sit
beside the sweep figures without a style break.
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK_SECONDARY, INK_MUTED = "#0b0b0b", "#52514e", "#898781"
GRIDLINE, BASELINE, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
CRITICAL, GOOD = "#d03b3b", "#0ca30c"

ENGINE_COLOR = {"azure-4.1-mini": BLUE, "google/gemma-4-e4b": ORANGE}
ENGINE_ORDER = ["azure-4.1-mini", "google/gemma-4-e4b"]
METHOD_LABEL = {
    "closed_book_llm": "closed-book LLM",
    "context_llm": "context LLM",
    "pipeline": "KG pipeline",
}
METHOD_ORDER = ["closed_book_llm", "context_llm", "pipeline"]

# Human-readable names for the ablation arms; the file stems say what changed, not what it means.
ARM_LABEL = {
    "nusmods__azure_4_1_mini__pipeline": "engine → azure-4.1-mini",
    "nusmods__gemma_4_e4b__pipeline__elt035": "link threshold → 0.35",
    "nusmods__gemma_4_e4b__pipeline__elt060": "link threshold → 0.60",
    "nusmods__azure_4_1_mini__pipeline__elt035": "link threshold → 0.35  (azure)",
    "nusmods__gemma_4_e4b__pipeline__fixed_cwa": "routing → fixed CWA",
    "nusmods__gemma_4_e4b__pipeline__fixed_owa": "routing → fixed OWA",
    "nusmods__gemma_4_e4b__pipeline__withhold": "withhold unresolved claims",
    "nusmods__gemma_4_e4b__pipeline__rep2": "replicate (same seed)",
}


def style(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    getattr(ax, f"{grid_axis}axis").grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)


def finish(fig, ax, title, subtitle, path):
    # Both offsets are in points, not axes fractions: an axes-fraction offset grows with figure
    # height, so on the tall ablation chart the subtitle rode up into the title.
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=22)
    if subtitle:
        ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction", xytext=(0, 5),
                    textcoords="offset points", color=INK_SECONDARY, fontsize=9.5, va="bottom")
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(f"  wrote {path}")


def reference_cells(cells):
    """The main-arm cells: one per (engine, method) at the selected threshold, dynamic routing.

    Both filters are load-bearing, because the map is keyed on (model, method) and a stray match
    silently overwrites the cell rather than erroring:

    * the dataset filter excludes the RMIT arms in `ablation/`, which carry method='pipeline',
      entity_link_threshold=None and the same model name;
    * the name-shape filter excludes NUSMods ablation arms that differ from the reference only in
      a setting this function does not inspect — `withhold` and the same-seed replicate both keep
      dynamic routing at threshold 0.95, so a value filter alone cannot separate them.
    """
    main = {}
    for cell in cells:
        # Main cells are `<dataset>__<model>__<method>`; ablation arms carry a fourth segment.
        if cell["dataset"] != "nusmods" or len(cell["name"].split("__")) != 3:
            continue
        if cell["routing_mode"] != "dynamic":
            continue
        if cell["method"] == "pipeline" and cell["entity_link_threshold"] not in (0.95, None):
            continue
        main[(cell["model"], cell["method"])] = cell
    return main


def chart_method_comparison(cells, out):
    """Grouped bars: accuracy per method, one bar per engine, 95% CI whiskers."""
    main = reference_cells(cells)
    engines = [e for e in ENGINE_ORDER if any(k[0] == e for k in main)]
    methods = [m for m in METHOD_ORDER if any(k[1] == m for k in main)]
    if not engines or not methods:
        return

    floor = next(iter(main.values()))["majority_floor"]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    style(ax)
    width = 0.36
    positions = range(len(methods))

    for slot, engine in enumerate(engines):
        offset = (slot - (len(engines) - 1) / 2) * width
        xs, ys, los, his = [], [], [], []
        for index, method in enumerate(methods):
            cell = main.get((engine, method))
            if not cell:
                continue
            xs.append(index + offset)
            ys.append(cell["accuracy"])
            los.append(cell["accuracy"] - cell["ci95"][0])
            his.append(cell["ci95"][1] - cell["accuracy"])
        ax.bar(xs, ys, width * 0.92, label=engine, color=ENGINE_COLOR[engine], zorder=3)
        ax.errorbar(xs, ys, yerr=[los, his], fmt="none", ecolor=INK_SECONDARY,
                    elinewidth=1.4, capsize=4, zorder=4)
        for x, y in zip(xs, ys):
            ax.text(x, y + 0.035, f"{y:.1%}", ha="center", color=INK, fontsize=9,
                    fontweight="bold", zorder=5)

    ax.axhline(floor, color=BASELINE, linewidth=1.6, linestyle="--", zorder=2)
    # To the right of the last group, in reserved margin: every inter-group gap is narrower than
    # this label, so placing it inside the plot puts it on top of a bar.
    ax.set_xlim(-0.55, len(methods) - 0.5 + 0.62)
    ax.text(len(methods) - 0.42, floor, f"majority-class floor\n{floor:.1%}",
            ha="left", va="center", color=INK_MUTED, fontsize=8.5)

    ax.set_xticks(list(positions))
    ax.set_xticklabels([METHOD_LABEL[m] for m in methods], color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY, loc="upper left")
    finish(fig, ax, "NUSMods: verification accuracy by method",
           "n = 500, bootstrap 95% CI. Structured verification against the catalog vs. the same "
           "model given flat triples or nothing.", out)


def chart_threshold(cells, ceiling, out):
    """Line: the entity-link threshold's effect, LLM-free ceiling vs. end-to-end."""
    thresholds = sorted(float(t) for t in ceiling["accuracy_by_threshold"])
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    style(ax)

    # The ceiling is a bound, not a third engine, so it takes a neutral dashed line rather than a
    # categorical hue — otherwise it competes for identity with the two engine series.
    ceiling_ys = [ceiling["accuracy_by_threshold"][str(t)] for t in thresholds]
    ax.plot(thresholds, ceiling_ys, color=INK_SECONDARY, linewidth=2, linestyle="--", marker="o",
            markersize=8, markeredgecolor=SURFACE, markeredgewidth=2,
            label="stage-3/4 ceiling (no LLM)", zorder=4)
    for x, y in zip(thresholds, ceiling_ys):
        ax.text(x, y + 0.035, f"{y:.1%}", ha="center", color=INK_SECONDARY, fontsize=9)

    for engine in ENGINE_ORDER:
        points = sorted(
            ((c["entity_link_threshold"], c["accuracy"]) for c in cells
             if c["model"] == engine and c["method"] == "pipeline"
             and c["routing_mode"] == "dynamic" and c["entity_link_threshold"] is not None),
            key=lambda p: p[0])
        if len(points) < 2:
            continue
        ax.plot([p[0] for p in points], [p[1] for p in points], color=ENGINE_COLOR[engine],
                linewidth=2, marker="o", markersize=9, markeredgecolor=SURFACE,
                markeredgewidth=2, label=f"end-to-end, {engine}", zorder=3)
        # The two engine series sit within 0.4 points of each other at both ends, so per-point
        # numbers overprint. Only the endpoint is annotated, stacked by series slot.
        slot = ENGINE_ORDER.index(engine)
        ax.text(points[0][0] - 0.012, points[0][1] - 0.018 - 0.042 * slot,
                f"{points[0][1]:.1%}  {engine}", ha="left", va="top",
                color=ENGINE_COLOR[engine], fontsize=9, fontweight="bold")

    ax.set_xlabel("entity_link_threshold", color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(0.55, 1.10)
    ax.set_xlim(min(thresholds) - 0.05, max(thresholds) + 0.05)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY, loc="lower right")
    finish(fig, ax, "NUSMods: the link threshold decides the Not-in-KG class",
           "Below 0.95 the linker snaps non-existent module codes onto real modules.", out)


def chart_reasoning_type(cells, out):
    """Horizontal grouped bars: per-construction accuracy, pipeline vs. flat-context baseline."""
    main = reference_cells(cells)
    engine = next((e for e in ENGINE_ORDER
                   if (e, "pipeline") in main and (e, "context_llm") in main), None)
    if not engine:
        return
    pipeline, context = main[(engine, "pipeline")], main[(engine, "context_llm")]
    types = sorted(pipeline["by_reasoning_type"], key=lambda t: -pipeline["by_reasoning_type"][t]["n"])

    fig, ax = plt.subplots(figsize=(8.8, 5.4))
    style(ax, grid_axis="x")
    height = 0.38
    for slot, (cell, label, color) in enumerate(
            ((context, "context LLM", ORANGE), (pipeline, "KG pipeline", BLUE))):
        offset = (slot - 0.5) * height
        ys = [i + offset for i in range(len(types))]
        xs = [cell["by_reasoning_type"].get(t, {"accuracy": 0})["accuracy"] for t in types]
        ax.barh(ys, xs, height * 0.92, label=label, color=color, zorder=3)
        for y, x in zip(ys, xs):
            ax.text(x + 0.012, y, f"{x:.0%}", va="center", color=INK, fontsize=8.5)
        # Direct label on the top pair instead of a legend box: every bar here runs to ~100%,
        # so a legend has nowhere to sit that is not on top of data.
        ax.text(0.012, ys[0], label, va="center", ha="left", color=SURFACE,
                fontsize=9, fontweight="bold", zorder=5)

    ax.set_yticks(range(len(types)))
    ax.set_yticklabels([f"{t}  (n={pipeline['by_reasoning_type'][t]['n']})" for t in types],
                       color=INK_SECONDARY, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.14)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    finish(fig, ax, f"NUSMods: accuracy by item construction ({engine})",
           "The separation is concentrated in value comparison, set-emptiness, and path traversal.",
           out)


def chart_ablation(comparisons, out):
    """Dot plot: paired accuracy delta against the reference arm, significance by McNemar.

    Restricted to arms that change ONE pipeline setting. The `closed_book` and `context` arms are
    different methods, not ablations, and their −58 to −66 point deltas compress every genuine
    ablation into an unreadable band around zero; figure 1 already carries them.
    """
    rows = [c for c in comparisons
            if c["same_sample_seed"] and "closed_book" not in c["arm"] and "context" not in c["arm"]]
    if not rows:
        return
    rows.sort(key=lambda c: c["delta"])
    labels = [ARM_LABEL.get(c["arm"], c["arm"].replace("nusmods__", "")) for c in rows]

    fig, ax = plt.subplots(figsize=(10.2, 0.62 * len(rows) + 2.6))
    style(ax, grid_axis="x")
    ax.axvline(0, color=BASELINE, linewidth=1.6, zorder=2)
    for index, comparison in enumerate(rows):
        delta = comparison["delta"]
        significant = comparison["mcnemar_p"] < 0.05
        color = (CRITICAL if delta < 0 else GOOD) if significant else INK_MUTED
        ax.hlines(index, 0, delta, color=color, linewidth=2, zorder=3)
        ax.plot([delta], [index], marker="o", markersize=10, color=color,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
        # Above the dot, not beside it: at the negative extreme a side label runs under the
        # y tick labels, and at zero it collides with the axis line.
        ax.text(delta, index - 0.26, f"{delta:+.1%}   p = {comparison['mcnemar_p']:.2g}",
                va="bottom", ha="center", color=INK, fontsize=9)

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels, color=INK_SECONDARY, fontsize=9)
    span = max(abs(c["delta"]) for c in rows) or 0.02
    ax.set_xlim(-span - 0.09, span + 0.09)
    ax.set_ylim(len(rows) - 0.5, -0.7)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    finish(fig, ax, "NUSMods ablations: paired accuracy delta",
           "vs. the reference arm (gemma · pipeline · threshold 0.95 · dynamic). Exact McNemar; "
           "grey = not significant.", out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default="output/experiments/nusmods_20260726")
    parser.add_argument("--ceiling", default="output/diagnostics/nusmods_stage4_ceiling.json")
    args = parser.parse_args()

    root = Path(args.dir)
    summary = json.loads((root / "analysis_summary.json").read_text(encoding="utf-8"))
    ceiling = json.loads(Path(args.ceiling).read_text(encoding="utf-8"))
    outdir = root / "analysis"
    outdir.mkdir(parents=True, exist_ok=True)

    cells = summary["cells"]
    chart_method_comparison(cells, outdir / "01_method_comparison.png")
    chart_threshold(cells, ceiling, outdir / "02_entity_link_threshold.png")
    chart_reasoning_type(cells, outdir / "03_reasoning_type.png")
    chart_ablation(summary["paired_comparisons"], outdir / "04_ablation_deltas.png")


if __name__ == "__main__":
    main()
