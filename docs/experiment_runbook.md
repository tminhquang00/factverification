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

Expected regression result: **183 tests pass**.

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

This stage makes **no model calls**. Everything below is reproducible from saved artifacts on a
laptop in a few minutes.

Gold comes from `scripts/intervention_gold.py` and is a function of the reference graph and the
condition graph only — no completeness declaration is read. The `--full_declaration` argument below
is *not* used for gold; it supplies the **stale** declaration to the `declared_stale` system arm.

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
  --output output/experiments/incompleteness_final_20260803/nusmods_rescore_intervention_gold.json
```

This writes four independent system arms per condition — `declared_oracle`, `declared_stale`,
`binary`, and `occupancy_<t>` — plus `world_truth` and `evidence_state` on every row. Check the
printed `gold anomalies:` line. It counts rows where a claim true in the reference world was read as
conflicting with the condition graph, which pure deletion cannot produce. The expected value is
`{'true_fact_reported_as_conflicting': 5}` — five rows from the single multi-hop triple
`MA4262 → MA2108S`. A materially larger count means either a condition graph is not a pure deletion
of the reference graph, or the evidence classifier has regressed on set-valued relations; in both
cases every downstream number is suspect.

```powershell
& .venv\Scripts\python.exe scripts/analyze_incompleteness_results.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_rescore_intervention_gold.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_rescore_intervention_gold_analysis.json `
  --iterations 1000 --seed 20260803
```

The analysis reports both `false_contradiction_rate` and `contradiction_rate_on_true_claims`, each
with clustered bootstrap intervals. **Report the latter as the headline safety number** — it does not
depend on any convention about how absence should be labelled.

Selective-risk diagnostic:

```powershell
& .venv\Scripts\python.exe scripts/calibrate_selective_risk.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_rescore_intervention_gold.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_rescore_intervention_gold_calibration.json `
  --calibration_fraction 0.5 --target_risk 0.05
```

Stage attribution:

```powershell
& .venv\Scripts\python.exe scripts/analyze_stage_attribution.py `
  --questions data/nusmods_questions_200.jsonl `
  --graph data/nusmods_graph.json `
  --declaration data/completeness_declarations/nusmods.json `
  --pilots `
    output/experiments/incompleteness_final_20260803/azure_self_fixed.json `
    output/experiments/incompleteness_final_20260803/gemma_self_authoritative.json `
    output/experiments/incompleteness_final_20260803/azure_gen_gemma_det_authoritative.json `
    output/experiments/incompleteness_final_20260803/gemma_gen_azure_det.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_stage_attribution_intervention_gold.json
```

It reports gold-link verification, linker + verifier, Stage 4 on extracted atoms, and end-to-end
expected-triple precision/recall/F1.

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

### 5.1 Rescoring the external baselines under the current gold

The flat-context and MiniCheck runs above saved their gold column using the old declaration-coupled
function. The **model predictions remain valid** — no model needs to be called again — so only the
gold column is recomputed:

```powershell
& .venv\Scripts\python.exe scripts/rescore_external_baselines.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_flat_azure.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_flat_azure_intervention_gold.json

& .venv\Scripts\python.exe scripts/rescore_external_baselines.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_flat_gemma.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_flat_gemma_intervention_gold.json

& .venv\Scripts\python.exe scripts/rescore_external_baselines.py `
  --input output/experiments/incompleteness_final_20260803/nusmods_minicheck.json `
  --output output/experiments/incompleteness_final_20260803/nusmods_minicheck_intervention_gold.json `
  --prediction_fields mapped_prediction
```

Each output keeps the previous label under `gold_previous_declaration_coupled`, so the effect of the
gold revision is auditable row by row. 130 of 3,000 rows change in each file.

These are the study's most informative arms, because the predictor — an LLM or an NLI-style checker
— has no connection whatsoever to the gold definition.

## 5.2 Multi-vendor model panel

Runs the oracle-context tri-state verifier across a panel spanning four vendors and a
nano-to-frontier capability range, to test whether correct abstention under incomplete evidence is a
capability that scales, a per-model idiosyncrasy, or a structural floor.

```powershell
& .venv\Scripts\python.exe scripts/run_model_panel.py --max_workers 10
```

Each model writes its own artifact and checkpoint under
`output/experiments/model_panel_20260803/`, so an interrupted panel resumes without repeating
completed models. Expect several hours: reasoning models (`gpt-5.*`, `azure-o3`) take roughly 40
minutes for their 1,200 calls, conventional models around 5–10 minutes.

```powershell
& .venv\Scripts\python.exe scripts/analyze_model_panel.py `
  --panel_dir output/experiments/model_panel_20260803 `
  --output output/experiments/model_panel_20260803/panel_analysis.json
```

Read `contradiction_rate_on_true_claims` **together with** `abstention_precision` and
`abstention_recall`. A model can drive the safety metric to zero by answering "unknown" to
everything, so the safety number alone is not evidence of good behaviour; `accuracy` at low retention
is the summary statistic that penalises both over- and under-abstention.

Cross-model comparisons must also read `run.sampling` in each artifact. The o-series, GPT-5/Azure-5
and newest Anthropic models reject `temperature=0` and run at a provider default, so part of any
difference between them and a temperature-0 model is sampling rather than capability. The panel
analysis lists the affected models under `sampling_confound`.

## 5.3 Retrieval recall versus the oracle-context assumption

Quantifies how optimistic the oracle-context arm is. Deterministic, no model calls.

```powershell
& .venv\Scripts\python.exe scripts/evaluate_retrieval_recall.py
```

Reports BM25 (with stopword removal and exact course-code promotion) and an optional dense rerank,
under two query modes: the question as generated (which carries the course code) and a title-only
rewrite. The oracle-context arm is equivalent to recall@1 = 100%, so the gap between that and the
measured numbers is the amount by which every oracle-context result is optimistic.

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
