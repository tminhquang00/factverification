# Experiment Runbook

**Updated:** 2026-08-03
**Canonical study directory:** `output/experiments/incompleteness_final_20260803/`

Run commands from the repository root with PowerShell. Do not cite an aggregate unless its row-level
source file, hashes, and failure counts are present.

## 1. Environment and validation

```powershell
& .venv\Scripts\python.exe -m pip install -r requirements-experiments.txt
& .venv\Scripts\python.exe -m unittest discover -s tests
```

Expected regression result: **101 tests pass**.

Local model configuration:

- LM Studio server: `http://localhost:1234/v1`
- model: `google/gemma-4-e4b`
- OpenAI-compatible API enabled

Hosted runs use provider `azure` and model `azure-4.1-mini`; required endpoint credentials come from
the existing `.env` configuration.

## 2. Rebuild inputs

Generate the current question sets:

```powershell
& .venv\Scripts\python.exe scripts/generate_nusmods_questions.py `
  --graph data/nusmods_graph.json --out data/nusmods_questions_200.jsonl `
  --seed 20260803 --limit 200

& .venv\Scripts\python.exe scripts/generate_rmit_questions.py `
  --graph data/rmit_graph.json --out data/rmit_questions_50.jsonl `
  --seed 20260803
```

Build three NUSMods deletion seeds. Repeat the command with seeds `20260803` and `20260804`.

```powershell
& .venv\Scripts\python.exe scripts/build_degraded_graphs.py `
  --graph data/nusmods_graph.json `
  --declaration data/completeness_declarations/nusmods.json `
  --outdir output/experiments/nusmods_degradation_final `
  --retention 1.0 0.95 0.90 0.80 0.50 0.20 `
  --modes random clustered --seed 20260802 --dataset_name nusmods
```

Build RMIT with retention `1.0 0.50 0.20`, graph `data/rmit_graph.json`, declaration
`data/completeness_declarations/rmit.json`, output
`output/experiments/rmit_degradation_final`, and the same three seeds.

Every condition must contain a graph, `completeness.json`, `deletion_log.jsonl`, and `manifest.json`.

## 3. Generate answers and decompose claims

The canonical NUSMods command shape is:

```powershell
& .venv\Scripts\python.exe scripts/run_incompleteness_pilot.py `
  --questions data/nusmods_questions_200.jsonl `
  --full_graph data/nusmods_graph.json `
  --full_declaration data/completeness_declarations/nusmods.json `
  --degraded_dir output/experiments/nusmods_degradation_final/seed_20260802/random__retention_050 `
  --provider azure --model azure-4.1-mini `
  --detector_provider azure --detector_model azure-4.1-mini `
  --limit 200 --max_workers 4 `
  --output output/experiments/incompleteness_final_20260803/azure_self_fixed.json
```

For the local self arm, set both provider/model pairs to
`local / google/gemma-4-e4b`. Cross-detector arms reuse the exact same answer list:

```powershell
& .venv\Scripts\python.exe scripts/run_incompleteness_pilot.py `
  <same input arguments> `
  --provider local --model google/gemma-4-e4b `
  --detector_provider azure --detector_model azure-4.1-mini `
  --reuse_answers output/experiments/incompleteness_final_20260803/gemma_self_final.json `
  --limit 200 --max_workers 2 `
  --output output/experiments/incompleteness_final_20260803/gemma_gen_azure_det.json
```

Use the symmetric configuration for Azure answers checked by Gemma. `--reuse_answers` runs only the
two decomposition passes and deterministic verification; it never regenerates the answers. After a
mapping-only repair, add `--reuse_decomposition <prior-run.json>` as well; this preserves the saved
answer text and both decomposition passes while rerunning only deterministic mapping and
verification. The final mapping-only outputs are `gemma_self_authoritative.json` and
`azure_gen_gemma_det_authoritative.json`.

RMIT uses `data/rmit_questions_50.jsonl`, `data/rmit_graph.json`, the RMIT declaration, the RMIT
50%-retention condition, and `--limit 50`.

## 4. Deterministic rescore and stage attribution

Rescore all saved atoms across every NUSMods deletion graph:

```powershell
& .venv\Scripts\python.exe scripts/rescore_incompleteness_sweep.py `
  --pilot `
    output/experiments/incompleteness_final_20260803/azure_self_fixed.json `
    output/experiments/incompleteness_final_20260803/gemma_self_authoritative.json `
    output/experiments/incompleteness_final_20260803/azure_gen_gemma_det_authoritative.json `
    output/experiments/incompleteness_final_20260803/gemma_gen_azure_det.json `
  --degradation_dir output/experiments/nusmods_degradation_final `
  --full_graph data/nusmods_graph.json `
  --full_declaration data/completeness_declarations/nusmods.json `
  --occupancy_thresholds 0.50 0.70 0.85 0.95 `
  --output output/experiments/incompleteness_final_20260803/nusmods_rescore_authoritative.json

& .venv\Scripts\python.exe scripts/analyze_incompleteness_results.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_rescore_authoritative.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_rescore_authoritative_analysis.json `
  --iterations 1000 --seed 20260803
```

Run `scripts/analyze_stage_attribution.py` with the full graph, declaration, questions, and the same
pilot list, writing `nusmods_stage_attribution_authoritative.json`. It reports gold-link
verification, linker + verifier, Stage 4 on extracted atoms, and end-to-end expected-triple
precision/recall/F1.

## 5. Baselines

Oracle-context LLM baseline:

```powershell
& .venv\Scripts\python.exe scripts/run_flat_context_incompleteness.py `
  --questions data/nusmods_questions_200.jsonl `
  --degradation_dir output/experiments/nusmods_degradation_final `
  --graph_filename nusmods_graph.json `
  --provider azure --model azure-4.1-mini `
  --seeds 20260803 --retentions 100 95 80 50 20 `
  --modes random clustered --max_workers 4 `
  --output output/experiments/incompleteness_final_20260803/nusmods_flat_azure.json
```

Analyze with `scripts/analyze_flat_context_results.py`. Run the same command with the local model for
the Gemma arm.

MiniCheck baseline:

```powershell
& .venv\Scripts\python.exe scripts/run_minicheck_incompleteness.py `
  --questions data/nusmods_questions_200.jsonl `
  --degradation_dir output/experiments/nusmods_degradation_final `
  --graph_filename nusmods_graph.json `
  --seeds 20260803 --retentions 100 95 80 50 20 `
  --modes random clustered `
  --output output/experiments/incompleteness_final_20260803/nusmods_minicheck.json

& .venv\Scripts\python.exe scripts/analyze_minicheck_results.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_minicheck.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_minicheck_analysis.json `
  --bootstrap 1000 --seed 20260803
```

MiniCheck is binary. Its `Unsupported -> Contradicted` mapping is intentionally naive and is used
only to measure the open-world false-contradiction failure.

## 6. Controls and public transfer

```powershell
& .venv\Scripts\python.exe scripts/evaluate_linker_nil.py `
  --sample_per_class 500 --seed 20260803 `
  --output output/experiments/incompleteness_final_20260803/linker_nil.json

& .venv\Scripts\python.exe scripts/run_benchmark_sweep.py `
  --run_id final_public_20260803_local --providers local `
  --rmit_limit 300 --public_limit 500 --max_workers 2 --max_parallel 1 `
  --sampling random prefix --sample_seed 20260803 --entity_link_threshold 0.95
```

Run `scripts/run_kg_destruction_control.py` for NUSMods and CoDEx and
`scripts/run_graph_destruction_control.py` for the RMIT set-valued control. The shuffled prediction
change must exceed `0.20`.

Recompute public aggregates from rows:

```powershell
& .venv\Scripts\python.exe scripts/summarize_rerun_results.py `
  --dir output/experiments/final_public_20260803_local `
  --out output/experiments/final_public_20260803_local/aggregate_summary.json
```

## 7. Completion checklist

- every requested cell has a row-level JSON artifact;
- process manifests have exit code zero; start-time code hashes are required for new cells. In the
  final artifact set, all local cells and the affected Azure NUSMods/RMIT reruns have them. The four
  earlier Azure CoDEx/FactKG cells predate hash capture and are retained as an explicit provenance
  exception because the later institutional mapping repair is schema-gated away from those data;
- `n_failed_calls`, unscored rows, and parse errors are reported, not hidden;
- requested and realized deletion retention are both available;
- all aggregates are regenerated from row-level data;
- the 101-test suite and graph-destruction gates pass;
- current status and final report identify limitations, especially mechanical gold and oracle context.
