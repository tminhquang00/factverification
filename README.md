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
              │  (Offline C(R) Profiles & Path Checks) │
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────┐
              │    Selective Abstention Calibration    │
              │ (Continuous NLI Margin Tie-Breaker)    │
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │  Final Tristate Report │
                      │  (Provenance & Flags)  │
                      └────────────────────────┘
```

1. **Draft Response Generation**: Collects natural language answers from an LLM.
2. **Claim Decomposition (Stage 2)**: Breaks draft responses into atomic factual tuples `(Subject, Relation, Object)` using self-consistency filtering.
3. **Entity Resolution & Relation Mapping (Stage 3)**: Dispatches linking across explicit reporting axes (**L0**: Gold IDs, **L1**: Bi-encoder, **L2**: Heuristics).
4. **Semantic Graph Verification (Stage 4)**: Evaluates triples against logic rules using offline background completeness profiles (`data/completeness_profiles/`).
5. **Selective Abstention**: Adjusts verdicts between `Contradicted` and `Not-in-KG` based on continuous tie-broken confidence score $S_{\text{cal}}$.

---

## 2. Core Claim Ladder

*   **C1 (World-Assumption Routing)**: Per-relation world-assumption routing dominates fixed CWA and fixed OWA on Knowledge Graphs with heterogeneous relation density.
*   **C2 (Selective Signal Integration)**: Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment.
*   **C3 (Tri-State Protocol Utility)**: Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can.
*   **C4 (Institutional Catalog Deployment)**: Post-hoc claim-level verification is deployable on closed institutional catalogs with a controlled false-contradiction rate.

---

## 3. Project Directory Structure

* `verification_pipeline.py`: Core implementation of the 4-stage fact-verification pipeline.
* `kg_store.py`: Local thread-safe catalog storage containing graph density estimation and relation lookup logic.
* `adapters/`: Data normalization loaders and adapters (`kg_adapter.py`, `factkg_adapter.py`, `codex_adapter.py`, `metaqa_adapter.py`, `catalog2_adapter.py`).
* `data/completeness_profiles/`: Offline background completeness profiles serialized per dataset.
* `scripts/`: Diagnostic and evaluation scripts:
  * `run_phase0_diagnostics.py`: E0.1 Shuffled-KG control, E0.2 Chance floors, E0.3 Denominator audit.
  * `generate_completeness_profiles.py`: Background profile generator.
  * `run_revised_experiments.py`: E2 Routing, E3 Denominator, E4 Threshold sweep, E5 Meta-confidence.
  * `generate_tristate_benchmarks.py`: Generates `CoDEx-S-Tri` and `MetaQA-Tri` benchmarks.
  * `evaluate_binary_trap.py`: Quantifies penalized abstentions on FactKG vs tri-state benchmarks.
  * `evaluate_baselines.py`: Evaluates baseline models across all datasets.
* `docs/`: Comprehensive project documentation index ([docs/README.md](file:///c:/Users/Admin/Desktop/crawler/docs/README.md)):
  * `docs/architecture/`: Pipeline design (`design.md`) and expert review (`system_expert_review.md`).
  * `docs/benchmarks/`: Benchmark evaluation results (`research_report.md`) and calibration report (`calibration_report.md`).
  * `docs/walkthrough.md`: Getting started guide and rerun instructions.

---

## 4. Execution Guidelines

Always execute scripts using the local virtual environment Python executable per `AGENTS.md`:

```powershell
# Run Phase 0 Diagnostics
& .venv\Scripts\python.exe scripts/run_phase0_diagnostics.py

# Build Offline Background Completeness Profiles
& .venv\Scripts\python.exe scripts/generate_completeness_profiles.py

# Generate Tri-State Benchmark Datasets
& .venv\Scripts\python.exe scripts/generate_tristate_benchmarks.py

# Run Core Claim Experiments (E2-E5)
& .venv\Scripts\python.exe scripts/run_revised_experiments.py

# Quantify Binary Benchmark Trap (E7)
& .venv\Scripts\python.exe scripts/evaluate_binary_trap.py

# Evaluate Baseline Suite (E9)
& .venv\Scripts\python.exe scripts/evaluate_baselines.py
```

---

## 5. Summary of Benchmark Results

| LLM Engine | Dataset | Sample Size ($n$) | Linking Axis | E2E Accuracy | 95% Confidence Interval | Coverage | Selective Accuracy |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **azure-4.1-mini** | **RMIT Handbook** | 300 | **L1** | **95.00%** | [92.33%, 97.33%] | 100.00% | **95.00%** |
| **azure-4.1-mini** | **Catalog2** | 200 | **L1** | **92.50%** | [88.50%, 96.00%] | 100.00% | **92.50%** |
| **azure-4.1-mini** | **FactKG** | 500 | **L0** | **80.00%** | [76.20%, 83.60%] | 52.40% | **71.76%** |
| **azure-4.1-mini** | **FactKG** | 500 | **L1** | **81.00%** | [77.40%, 84.40%] | 52.20% | **74.33%** |
| **azure-4.1-mini** | **CoDEx-S** | 500 | **L1** | **37.20%** | [33.00%, 41.40%] | 100.00% | **37.20%** |
| **azure-4.1-mini** | **MetaQA** | 219 | **L1** | **37.90%** | [31.50%, 44.30%] | 100.00% | **37.90%** |
| **google/gemma-4-e4b** | **Catalog2** | 200 | **L1** | **66.00%** | [58.00%, 72.67%] | 100.00% | **66.00%** |
| **google/gemma-4-e4b** | **FactKG** | 500 | **L1** | **80.00%** | [76.40%, 83.60%] | 36.00% | **87.22%** |
| **google/gemma-4-e4b** | **CoDEx-S** | 500 | **L1** | **36.60%** | [32.40%, 40.80%] | 100.00% | **36.60%** |
| **google/gemma-4-e4b** | **MetaQA** | 219 | **L1** | **36.53%** | [30.10%, 43.00%] | 100.00% | **36.53%** |

