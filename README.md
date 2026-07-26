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
*   **C4 (Institutional Catalog Deployment)**: Post-hoc claim-level verification is deployable on closed institutional catalogs with a controlled false-contradiction rate. — **Partially supported.** The rate is still not *controlled*: confidence is uncalibrated and no calibration split is collected. The RMIT benchmark remains circular (`eval_rmit.py:54` verifies a template interpolated from the fields the verifier queries), so it measures template round-tripping. The **NUSMods** benchmark added 2026-07-26 removes that circularity and scales the catalog from 219 to 11,647 entities: it passes the graph-destruction gate (0.2907 mean prediction change), its closed-book baseline scores exactly the majority floor, and the pipeline beats a same-model flat-context baseline by +27.4 points. It is deliberately blind to C1 and says nothing about calibration. See [docs/benchmarks/nusmods_benchmark.md](docs/benchmarks/nusmods_benchmark.md).

---

## 3. Project Directory Structure

* `verification_pipeline.py`: Core implementation of the 4-stage fact-verification pipeline.
* `kg_store.py`: Local thread-safe catalog storage containing relation occupancy estimation and relation lookup logic.
* `adapters/`: Data normalization loaders and adapters (`kg_adapter.py`, `factkg_adapter.py`, `codex_adapter.py`, `metaqa_adapter.py`, `catalog2_adapter.py`, `nusmods_adapter.py`).
* `data/completeness_profiles/`: Offline per-dataset relation occupancy profiles. **Not consumed by `VerificationPipeline`** — only `Catalog2Adapter` reads them; stage-4 routing computes occupancy live from the loaded graph.
* `scripts/`: Diagnostic and evaluation scripts:
  * `run_benchmark_sweep.py`: Runs every benchmark cell as a parallel subprocess and writes a process manifest.
  * `summarize_rerun_results.py`: Recomputes every aggregate from row-level predictions.
  * `compare_runs.py`: Paired pre/post comparison and run-to-run prediction flip rates.
  * `run_kg_destruction_control.py`: **Grounding gate.** Shuffles graph content and fails if predictions barely move. `--benchmark {codex,nusmods}`.
  * `diagnose_object_namespace.py`: Isolates stage-3 object-namespace handling with no LLM.
  * `download_nusmods.py` → `parse_nusmods.py` → `build_nusmods_benchmark.py`: NUSMods catalog pipeline (fetch → 11,647-module graph → tri-state benchmark).
  * `diagnose_nusmods_stage4.py`: Stage-3/4 ceiling on NUSMods with no LLM; also selects `entity_link_threshold`.
  * `sweep_entity_threshold.py`: Selects `entity_link_threshold` on a held-out split.
  * `run_graph_destruction_control.py`: Paired destruction control for the deterministic completeness component.
  * `generate_completeness_profiles.py`: Background profile generator.
  * *(`evaluate_baselines.py` deleted 2026-07-26 — it returned hard-coded constants, not measurements. Registry: `e9_baseline_suite` / `invalidated_fabricated`. Baselines are measured through `eval_harness.py --method {closed_book_llm,context_llm}`.)*
* `docs/`: Comprehensive project documentation index ([docs/README.md](file:///c:/Users/Admin/Desktop/crawler/docs/README.md)):
  * `docs/journal_20260726.md`: **Start here for 2026-07-26.** Single-document synthesis of every experiment run that day — defect repairs, evaluation-substrate repairs, and the NUSMods benchmark — with consistent, cross-checked numbers.
  * `docs/architecture/`: Pipeline design (`design.md`) and expert review (`system_expert_review.md`).
  * `docs/benchmarks/`: Benchmark evaluation reports, current and superseded (see [docs/README.md](docs/README.md) for which is which).
  * `docs/experiment_runbook.md`: Exact PowerShell commands for every experiment, with saved-output paths and the flags that change what is measured.

---

## 4. Execution Guidelines

Always execute scripts using the local virtual environment Python executable per `AGENTS.md`:

```powershell
# 1. Regression suite (expect 77 passing)
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

Current study: **[docs/benchmarks/rerun_20260726_cleangraph_paper.md](docs/benchmarks/rerun_20260726_cleangraph_paper.md)**
(`rerun_20260726_cleangraph`, status `candidate`), which supersedes
[`rerun_20260726_paper.md`](docs/benchmarks/rerun_20260726_paper.md) — that earlier run's CoDEx and
MetaQA graphs carried fabricated course scaffolding on every entity (registry:
`public_graph_course_scaffolding_contamination`), since removed. All aggregates below are recomputed
from row-level predictions; every cell reports zero unscored rows. A single synthesized read of this
table plus the NUSMods results below is in
**[docs/journal_20260726.md](docs/journal_20260726.md)**.

| LLM Engine | Dataset | Sampling | $n$ | Accuracy | 95% CI | Majority floor |
|:---|:---|:---|:---:|:---:|:---:|:---:|
| **azure-4.1-mini** | **CoDEx** | random | 500 | **83.00%** | [79.40%, 86.20%] | 34.60% |
| **azure-4.1-mini** | **CoDEx** | prefix | 500 | **82.20%** | [78.80%, 85.60%] | 36.40% |
| **google/gemma-4-e4b** | **CoDEx** | random | 500 | **77.40%** | [73.60%, 80.80%] | 34.60% |
| **google/gemma-4-e4b** | **CoDEx** | prefix | 500 | **75.80%** | [71.80%, 79.60%] | 36.40% |
| **azure-4.1-mini** | **FactKG** | random | 500 | 58.20% | [54.00%, 62.40%] | 52.80% |
| **azure-4.1-mini** | **FactKG** | prefix | 500 | 83.20% | [80.00%, 86.20%] | 64.60% |
| **google/gemma-4-e4b** | **FactKG** | random | 500 | 56.60% | [52.00%, 60.60%] | 52.80% |
| **google/gemma-4-e4b** | **FactKG** | prefix | 500 | 81.40% | [78.00%, 85.00%] | 64.60% |
| **azure-4.1-mini** | **RMIT** | full | 300 | 97.33% | [95.30%, 99.00%] | 41.67% |
| **google/gemma-4-e4b** | **RMIT** | full | 300 | 89.00% | [85.70%, 92.30%] | 41.67% |

> [!IMPORTANT]
> **Read the sampling column.** `data/factkg_test.jsonl` is sorted into contiguous reasoning-type
> blocks, so `prefix` (the historical `data[:500]`) selects 2 of 13 reasoning types at a majority
> floor of 64.60% against the full set's 51.35%. The two FactKG arms differ by ~25 points on
> identical code. CoDEx's arms are comparable (floors 36.4% vs 34.6%).
>
> **RMIT is circular** (`eval_rmit.py:54` verifies a template interpolated from the fields the
> verifier queries) and measures template round-tripping, not advising accuracy.
>
> **Only the four FactKG rows are paired against the pre-cleangraph run** — its rows were not
> regenerated. CoDEx and RMIT rows changed (graph rebuilt, RMIT redrawn under a seed for the first
> time), so their deltas versus the previous study are not attributable to the de-scaffolding fix.
> See [docs/journal_20260726.md §3.3](docs/journal_20260726.md#33-evaluation-substrate-validity).

### NUSMods (institutional catalog, added 2026-07-26)

Separate study, not part of the sweep above. 11,647 NUS modules from the NUSMods v2 API; every gold
label is world-assumption-independent, so the benchmark cannot score the verifier's own routing
policy. $n=500$, identical rows in every cell, `--entity_link_threshold 0.95`, zero unscored rows.
Majority-class floor 33.80%.

| Method | azure-4.1-mini | google/gemma-4-e4b | engine gap (paired) |
|:---|---:|---:|---:|
| `closed_book_llm` | 41.00% | 33.80% | +7.20 |
| `context_llm` | 90.80% | 72.00% | **+18.80** ($p = 9.5\times10^{-24}$) |
| **`pipeline`** | **99.80%** | **99.40%** | **+0.40** ($p = 0.625$, n.s.) |

**The pipeline erases the engine gap.** A 4B local model matches a hosted frontier-class model once
the graph does the comparison, while the same two models differ by 18.80 points on flat triple
context. The advantage over the context baseline is concentrated in closed-world set reasoning
(`prerequisite-negation`: 100% vs 66%), not in value lookup.

Graph-destruction gate **PASS** (0.2907 mean prediction change, gate 0.20). The ablation suite
finds exactly one knob that matters: `entity_link_threshold` is worth −25.00 points at 0.35 and
0.60 on both engines (it deletes the `Not-in-KG` class), while fixed-CWA/fixed-OWA routing,
unresolved-claim withholding, and a same-seed replicate each move 0–1 rows of 500. Run-to-run flip
rate 0.10%.

Caveats — the headline sits at the stage-3/4 ceiling of 100.00% and so discriminates poorly between
competent systems; `Supported` items are still template-derived from the queried fields; and the
benchmark is deliberately blind to C1 (confirmed: forcing fixed OWA changes 0 of 500 predictions).

Full paper: [docs/benchmarks/nusmods_study_20260726.md](docs/benchmarks/nusmods_study_20260726.md) ·
construction reference: [docs/benchmarks/nusmods_benchmark.md](docs/benchmarks/nusmods_benchmark.md)

### Effect of the verification-logic repairs, sampling held constant

These are the pipeline-logic corrections (entity/value representation, entity-link threshold,
relation-name matching, unresolved-claim voting, crash scoring) fixed *before* the evaluation-substrate
repair that produced the §5 table above — "After" here is that intermediate state, not the current
numbers. See [docs/journal_20260726.md §3.2](docs/journal_20260726.md#32-verification-logic-validity).

| Cell | Before | After | Δ |
|:---|---:|---:|---:|
| CoDEx / `azure-4.1-mini` | 41.80% | 81.80% | **+40.0** |
| CoDEx / `gemma-4-e4b` | 37.20% | 75.80% | **+38.6** |
| FactKG / `azure-4.1-mini` | 80.20% | 83.60% | +3.4 |
| FactKG / `gemma-4-e4b` | 79.80% | 82.60% | +2.8 |
| RMIT / `azure-4.1-mini` | 97.33% | 97.33% | 0.00 |
| RMIT / `gemma-4-e4b` | 92.33% | 90.33% | −2.00 |

CoDEx `Supported` recall moved **0.039 → 0.981**. The graph-destruction control moved from 1.8–2.8%
to **28.9%** prediction change, establishing graph-groundedness for the LLM pipeline for the first
time. RMIT is unchanged for `azure-4.1-mini`; the `gemma-4-e4b` delta is inside the measured
run-to-run noise floor and is not claimed as a change. FactKG's +3.4 / +2.8 are at the resolution
limit and are directional only. The subsequent S1–S5 substrate repair (§5 above) then moved paired
accuracy by at most 1.2 points on top of this — a construct-validity fix, not a further accuracy
gain. See [docs/journal_20260726.md](docs/journal_20260726.md) for the full before/after/after chain.

