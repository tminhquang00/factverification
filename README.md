# Knowledge Graph (KG) Fact-Verification Framework

This repository implements an end-to-end, tri-state, claim-level factual verification pipeline. The system validates natural language assertions against structured Knowledge Graphs using local or remote LLMs, dynamic world-assumption routing, and calibrated selective abstention.

---

## 1. Pipeline Overview

The fact-verification pipeline runs in four core stages:

```
                  ┌─────────────────────────────────┐
                  │ Draft Answer (Natural Language) │
                  └────────────────┬────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────┐
              │    Stage 2: Atomic Claim Extraction    │
              │  (Schema-Guided & Double-Run Checked)  │
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────┐
              │  Stage 3: Entity & Relation Resolving  │
              │  (L0: Oracle, L1: Bi-Encoder, L2: Token)│
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────┐
              │  Stage 4: Factual Graph Verification   │
              │  (CWA/OWA on live relation occupancy)  │
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │  Final Tristate Report │
                      │  (uncalibrated conf.)  │
                      └────────────────────────┘
```

1. **Draft Response Generation**: Collects natural language answers from an LLM.
2. **Claim Decomposition (Stage 2)**: Breaks draft responses into atomic factual tuples `(Subject, Relation, Object)` using self-consistency filtering.
3. **Entity Resolution & Relation Mapping (Stage 3)**: Dispatches linking across explicit reporting axes (**L0**: Gold IDs, **L1**: Bi-encoder, **L2**: Heuristics). Subject links below `entity_link_threshold` are reported unresolved rather than snapped to a nearest neighbour, and objects are returned in the graph's own value namespace (surface labels), not as entity keys.
4. **Semantic Graph Verification (Stage 4)**: Evaluates triples against relation-dispatched logic rules, routing per relation between closed- and open-world semantics using *live* relation occupancy from `KGStore`. Under closed-world an absent fact yields `Contradicted`; under open-world, `Not-in-KG`.

> [!WARNING]
> **Confidence is uncalibrated and there is no NLI component.** `calculate_confidence` returns a
> heuristic product with no fitted mapping to correctness; every result row carries
> `confidence_calibrated: false`. Coverage and selective accuracy are descriptive statistics at one
> operating point, never risk guarantees. Earlier revisions of this file and of
> `docs/architecture/` described an "offline C(R) profile" feeding Stage 4 and a "continuous NLI
> margin tie-breaker" — neither exists in the execution path. See
> [docs/architecture/system_expert_review.md §6](docs/architecture/system_expert_review.md).

---

## 2. Core Claim Ladder

These are the study's *target* claims. Evidence status as of 2026-07-26 is marked on each.

*   **C1 (World-Assumption Routing)**: Per-relation world-assumption routing dominates fixed CWA and fixed OWA on Knowledge Graphs with heterogeneous relation density. — **Unevaluated.** The `fixed_cwa` / `fixed_owa` treatments exist but no valid paired ablation has been run (registry: `implementation_repaired_requires_rerun`).
*   **C2 (Selective Signal Integration)**: Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment. — **Not testable as written.** There is no NLI component in the codebase, and routing uses occupancy rather than completeness.
*   **C3 (Tri-State Protocol Utility)**: Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can. — **Supported.** FactKG collapses `Not-in-KG`/`Out-of-scope`/`Abstained` into `Contradicted`, and its reasoning types are near-perfectly label-confounded, so a `Contradicted` prior scores 0.94–1.00 on one type group and 0.03–0.33 on the other.
*   **C4 (Institutional Catalog Deployment)**: Post-hoc claim-level verification is deployable on closed institutional catalogs with a controlled false-contradiction rate. — **Not supported.** No rate is *controlled*: confidence is uncalibrated and no calibration split is collected. The institutional benchmark is also circular (`eval_rmit.py:54` verifies a template interpolated from the fields the verifier queries), so it measures template round-tripping rather than advising quality.

---

## 3. Project Directory Structure

* `verification_pipeline.py`: Core implementation of the 4-stage fact-verification pipeline.
* `kg_store.py`: Local thread-safe catalog storage containing relation occupancy estimation and relation lookup logic.
* `adapters/`: Data normalization loaders and adapters (`kg_adapter.py`, `factkg_adapter.py`, `codex_adapter.py`, `metaqa_adapter.py`, `catalog2_adapter.py`).
* `data/completeness_profiles/`: Offline per-dataset relation occupancy profiles. **Not consumed by `VerificationPipeline`** — only `Catalog2Adapter` reads them; stage-4 routing computes occupancy live from the loaded graph.
* `scripts/`: Diagnostic and evaluation scripts:
  * `run_benchmark_sweep.py`: Runs every benchmark cell as a parallel subprocess and writes a process manifest.
  * `summarize_rerun_results.py`: Recomputes every aggregate from row-level predictions.
  * `compare_runs.py`: Paired pre/post comparison and run-to-run prediction flip rates.
  * `run_kg_destruction_control.py`: **Grounding gate.** Shuffles graph content and fails if predictions barely move.
  * `diagnose_object_namespace.py`: Isolates stage-3 object-namespace handling with no LLM.
  * `sweep_entity_threshold.py`: Selects `entity_link_threshold` on a held-out split.
  * `run_graph_destruction_control.py`: Paired destruction control for the deterministic completeness component.
  * `generate_completeness_profiles.py`: Background profile generator.
  * `evaluate_baselines.py`: Evaluates baseline models across all datasets.
* `docs/`: Comprehensive project documentation index ([docs/README.md](file:///c:/Users/Admin/Desktop/crawler/docs/README.md)):
  * `docs/architecture/`: Pipeline design (`design.md`) and expert review (`system_expert_review.md`).
  * `docs/benchmarks/`: Benchmark evaluation results (`research_report.md`) and calibration report (`calibration_report.md`).
  * `docs/walkthrough.md`: Getting started guide and rerun instructions.

---

## 4. Execution Guidelines

Always execute scripts using the local virtual environment Python executable per `AGENTS.md`:

```powershell
# 1. Regression suite (expect 35 passing)
& .venv\Scripts\python.exe -m unittest discover -s tests

# 2. Stage-3 diagnostics — deterministic, no LLM, seconds to run
& .venv\Scripts\python.exe -m scripts.diagnose_object_namespace --thresholds 0.35 0.95
& .venv\Scripts\python.exe -m scripts.sweep_entity_threshold

# 3. Grounding gate — fails if predictions survive destroying the graph's content
& .venv\Scripts\python.exe -m scripts.run_kg_destruction_control --entity_link_threshold 0.95

# 4. Full benchmark sweep (all cells, both sampling modes, parallel subprocesses)
& .venv\Scripts\python.exe scripts/run_benchmark_sweep.py --run_id <new_run_id>

# 5. Recompute every aggregate from row-level predictions
& .venv\Scripts\python.exe scripts/summarize_rerun_results.py `
    --dir output\experiments\<new_run_id> `
    --out output\experiments\<new_run_id>\aggregate_summary.json
```

See [docs/experiment_runbook.md](docs/experiment_runbook.md) for the flags that change what is
measured (`--sample`, `--sample_seed`, `--entity_link_threshold`).

---

## 5. Summary of Benchmark Results

Current study: **[docs/benchmarks/rerun_20260726_paper.md](docs/benchmarks/rerun_20260726_paper.md)**
(`rerun_20260726_fixed`, status `candidate`). All aggregates are recomputed from row-level
predictions; every cell reports zero unscored rows.

| LLM Engine | Dataset | Sampling | $n$ | Accuracy | 95% CI | Majority floor | Coverage | Selective Acc. |
|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **azure-4.1-mini** | **CoDEx** | random | 500 | **83.80%** | [80.40%, 87.00%] | 35.00% | 99.60% | **83.90%** |
| **azure-4.1-mini** | **CoDEx** | prefix | 500 | **81.80%** | [78.20%, 85.00%] | 35.80% | 99.80% | **81.80%** |
| **google/gemma-4-e4b** | **CoDEx** | random | 500 | **78.60%** | [75.00%, 82.60%] | 35.00% | 91.20% | **82.24%** |
| **google/gemma-4-e4b** | **CoDEx** | prefix | 500 | **75.80%** | [72.00%, 79.40%] | 35.80% | 89.20% | **79.37%** |
| **azure-4.1-mini** | **FactKG** | random | 500 | 57.60% | [53.20%, 61.80%] | 52.80% | 69.40% | 58.50% |
| **azure-4.1-mini** | **FactKG** | prefix | 500 | 83.60% | [80.40%, 86.60%] | 64.60% | 62.20% | 77.17% |
| **google/gemma-4-e4b** | **FactKG** | random | 500 | 55.80% | [51.20%, 60.20%] | 52.80% | 62.80% | 59.55% |
| **google/gemma-4-e4b** | **FactKG** | prefix | 500 | 82.60% | [79.40%, 85.60%] | 64.60% | 46.60% | 87.55% |
| **azure-4.1-mini** | **RMIT** | full | 300 | 97.33% | [95.33%, 99.00%] | 41.67% | 97.67% | 99.66% |
| **google/gemma-4-e4b** | **RMIT** | full | 300 | 90.33% | [86.67%, 93.67%] | 41.67% | 95.67% | 94.42% |

> [!IMPORTANT]
> **Read the sampling column.** `data/factkg_test.jsonl` is sorted into contiguous reasoning-type
> blocks, so `prefix` (the historical `data[:500]`) selects 2 of 13 reasoning types at a majority
> floor of 64.60% against the full set's 51.35%. The two FactKG arms differ by ~26 points on
> identical code. CoDEx's arms are comparable (floors 35.8% vs 35.0%).
>
> **RMIT is circular** (`eval_rmit.py:54` verifies a template interpolated from the fields the
> verifier queries) and measures template round-tripping, not advising accuracy.

### Effect of the 2026-07-26 repairs, sampling held constant

| Cell | Before | After | Δ |
|:---|---:|---:|---:|
| CoDEx / `azure-4.1-mini` | 41.80% | **81.80%** | **+40.0** |
| CoDEx / `gemma-4-e4b` | 37.20% | **75.80%** | **+38.6** |
| FactKG / `azure-4.1-mini` | 80.20% | 83.60% | +3.4 |
| FactKG / `gemma-4-e4b` | 79.80% | 82.60% | +2.8 |
| RMIT / `azure-4.1-mini` | 97.33% | 97.33% | 0.00 |
| RMIT / `gemma-4-e4b` | 92.33% | 90.33% | −2.00 |

CoDEx `Supported` recall moved **0.039 → 0.981**. The graph-destruction control moved from 1.8–2.8%
to **28.9%** prediction change, establishing graph-groundedness for the LLM pipeline. RMIT is
unchanged for `azure-4.1-mini`; the `gemma-4-e4b` delta is inside the measured run-to-run noise
floor and is not claimed as a change. FactKG's +3.4 / +2.8 are at the resolution limit and are
directional only.

