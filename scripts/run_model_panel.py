"""Run the oracle-context tri-state verifier across a multi-vendor model panel.

Why this experiment exists
--------------------------
The two-model study could observe that a tri-state prompt helps unequally — it cut the
contradiction rate on true claims 2.7x for the hosted model but only 1.13x for the local one — but
two models cannot distinguish three very different explanations:

1. **Capability scaling.** Bigger/stronger models abstain correctly, so the gap closes over time on
   its own and needs no engineering intervention.
2. **Idiosyncrasy.** Abstention behaviour varies by vendor and training recipe rather than by
   capability, so no amount of model progress reliably fixes it.
3. **A floor.** Every model, however strong, retains a substantial contradiction rate on true
   claims under severe incompleteness, so explicit metadata is structurally necessary.

Distinguishing these requires a panel spanning several vendors and a wide capability range. This
script runs the same fixed protocol — identical claims, identical oracle-selected evidence,
identical prompt, identical declaration-independent gold — across every model given, so the only
thing varying is the model.

Design notes
------------
* The verifier arm is used rather than the long-form arm on purpose. In the flat-context arm the
  predictor is an LLM and gold comes from graph contents alone, so the model has no influence over
  its own answer key. It is the cleanest independent measurement in the study.
* Evidence is oracle-selected. That is generous to the models and makes the results an upper bound
  on what a retrieval-based deployment would achieve.
* Not every model honours ``temperature=0``. The o-series, the GPT-5/Azure-5 families and the newest
  Anthropic models run at a provider default. Each per-model artifact records its resolved sampling
  under ``run.sampling``, and the panel summary aggregates which models were affected, so the
  confound stays visible instead of being averaged away.
* Each model writes its own artifact and its own checkpoint, so an interrupted panel resumes without
  repeating completed models.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Panel spanning four vendors and a nano-to-frontier capability range. azure-4.1-mini is retained
# for continuity with the original two-model study.
DEFAULT_PANEL = [
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "azure-4.1",
    "azure-4.1-mini",
    "azure-4o-mini",
    "azure-o3",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "llama-3.3-70b",
]

# Coarse vendor/tier labels used only for grouping in the analysis. They are editorial, recorded in
# the artifact so a reader can disagree with them without re-running anything.
MODEL_METADATA = {
    "gpt-5.5":               {"vendor": "OpenAI",    "tier": "frontier"},
    "gpt-5.4":               {"vendor": "OpenAI",    "tier": "large"},
    "gpt-5.4-mini":          {"vendor": "OpenAI",    "tier": "mid"},
    "gpt-5.4-nano":          {"vendor": "OpenAI",    "tier": "small"},
    "azure-4.1":             {"vendor": "OpenAI",    "tier": "large"},
    "azure-4.1-mini":        {"vendor": "OpenAI",    "tier": "mid"},
    "azure-4o-mini":         {"vendor": "OpenAI",    "tier": "small"},
    "azure-o3":              {"vendor": "OpenAI",    "tier": "reasoning"},
    "azure-o4-mini":         {"vendor": "OpenAI",    "tier": "reasoning"},
    "azure-5":               {"vendor": "OpenAI",    "tier": "large"},
    "azure-5-mini":          {"vendor": "OpenAI",    "tier": "mid"},
    "azure-5.2":             {"vendor": "OpenAI",    "tier": "large"},
    "azure-4o":              {"vendor": "OpenAI",    "tier": "large"},
    "claude-opus-4-7":       {"vendor": "Anthropic", "tier": "frontier"},
    "claude-opus-4-6":       {"vendor": "Anthropic", "tier": "frontier"},
    "claude-opus-4-5":       {"vendor": "Anthropic", "tier": "large"},
    "claude-sonnet-4-6":     {"vendor": "Anthropic", "tier": "mid"},
    "claude-sonnet-4-5":     {"vendor": "Anthropic", "tier": "mid"},
    "claude-haiku-4-5":      {"vendor": "Anthropic", "tier": "small"},
    "gemini-2.5-pro":        {"vendor": "Google",    "tier": "large"},
    "gemini-2.5-flash":      {"vendor": "Google",    "tier": "mid"},
    "gemini-2.5-flash-lite": {"vendor": "Google",    "tier": "small"},
    "llama-3.3-70b":         {"vendor": "Meta",      "tier": "open-weights"},
}


def run_one(model, args):
    output = Path(args.output_dir) / f"flat_{model.replace('/', '_')}.json"
    if output.exists() and not args.force:
        return {"model": model, "status": "cached", "output": str(output)}

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_flat_context_incompleteness.py"),
        "--questions", args.questions,
        "--degradation_dir", args.degradation_dir,
        "--graph_filename", args.graph_filename,
        "--reference_graph", args.reference_graph,
        "--provider", "azure",
        "--model", model,
        "--seeds", str(args.seed),
        "--retentions", *[str(value) for value in args.retentions],
        "--modes", *args.modes,
        "--max_workers", str(args.max_workers),
        "--output", str(output),
    ]
    started = time.time()
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    elapsed = round(time.time() - started, 1)
    if completed.returncode != 0:
        return {
            "model": model,
            "status": "failed",
            "returncode": completed.returncode,
            "elapsed_seconds": elapsed,
            "stderr_tail": completed.stderr[-1500:],
        }
    return {"model": model, "status": "ok", "elapsed_seconds": elapsed, "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=DEFAULT_PANEL)
    parser.add_argument("--questions", default="data/nusmods_questions_200.jsonl")
    parser.add_argument("--degradation_dir", default="output/experiments/nusmods_degradation_final")
    parser.add_argument("--graph_filename", default="nusmods_graph.json")
    parser.add_argument("--reference_graph", default="data/nusmods_graph.json")
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--retentions", type=int, nargs="+", default=[100, 80, 50, 20])
    parser.add_argument("--modes", nargs="+", default=["random"])
    parser.add_argument("--max_workers", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output_dir", default="output/experiments/model_panel_20260803")
    args = parser.parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    results = []
    for index, model in enumerate(args.models, start=1):
        print(f"[{index}/{len(args.models)}] {model} ...", flush=True)
        result = run_one(model, args)
        result["metadata"] = MODEL_METADATA.get(model, {"vendor": "unknown", "tier": "unknown"})
        results.append(result)
        print(f"    {result['status']} ({result.get('elapsed_seconds', 0)}s)", flush=True)
        if result["status"] == "failed":
            print(result["stderr_tail"], flush=True)

    manifest = {
        "panel": args.models,
        "protocol": {
            "arm": "oracle-context tri-state verifier (flat context)",
            "seed": args.seed,
            "retentions": args.retentions,
            "modes": args.modes,
            "questions": args.questions,
            "reference_graph": args.reference_graph,
            "gold": "scripts/intervention_gold.py (no completeness declaration is read)",
            "evidence_selection": "oracle: records chosen from the known expected triple",
            "requested_temperature": 0.0,
        },
        "results": results,
    }
    manifest_path = Path(args.output_dir) / "panel_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    ok = sum(r["status"] in {"ok", "cached"} for r in results)
    print(f"\n{ok}/{len(results)} models completed; manifest at {manifest_path}")


if __name__ == "__main__":
    main()
