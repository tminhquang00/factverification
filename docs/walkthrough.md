# Verification Walkthrough & Revised Benchmark Summary

This document provides a comprehensive overview of the Knowledge Graph Verification Framework, revised experiment design, diagnostic gates, linking condition axes, and evaluation benchmarks across five target datasets.

---

## 1. Project Structure & Core Modules

All documentation and reports are located in the [docs/](file:///c:/Users/Admin/Desktop/crawler/docs) directory:
- [design.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/design.md): Ontological schema, KGAdapter architecture, and pipeline design guidelines.
- [research_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report.md): Restructured report around 4 core claims (**C1**, **C2**, **C3**, **C4**) and diagnostic findings.
- [calibration_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/calibration_report.md): 5-fold cross-fitted meta-confidence, AURC curves, and False Contradiction Rate (FCR).
- [system_expert_review.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/system_expert_review.md): Implementation algorithms, linking axes (**L0, L1, L2**), and data flows.

The core codebase resides in the root directory:
- [verification_pipeline.py](file:///c:/Users/Admin/Desktop/crawler/verification_pipeline.py): The 4-stage post-hoc claim verifier with bi-encoder entity resolution and relation mapping.
- [adapters/kg_adapter.py](file:///c:/Users/Admin/Desktop/crawler/adapters/kg_adapter.py): Protocol abstraction for entity linking, relation mapping, and offline background KG completeness profiling (`data/completeness_profiles/`).
- [kg_store.py](file:///c:/Users/Admin/Desktop/crawler/kg_store.py): Thread-safe catalog database with BFS graph path traversal.
- [scripts/run_phase0_diagnostics.py](file:///c:/Users/Admin/Desktop/crawler/scripts/run_phase0_diagnostics.py): Phase 0 diagnostic gate (E0.1 Shuffled-KG control, E0.2 Chance floors, E0.3 Denominator audit).
- [scripts/run_revised_experiments.py](file:///c:/Users/Admin/Desktop/crawler/scripts/run_revised_experiments.py): Core claim experiments (E2 Routing, E3 Denominator, E4 Threshold sweep, E5 5-Fold Meta-Confidence).
- [scripts/generate_tristate_benchmarks.py](file:///c:/Users/Admin/Desktop/crawler/scripts/generate_tristate_benchmarks.py): E6 Tri-state benchmark generation.
- [scripts/evaluate_binary_trap.py](file:///c:/Users/Admin/Desktop/crawler/scripts/evaluate_binary_trap.py): E7 Binary benchmark trap evaluation.
- [scripts/evaluate_baselines.py](file:///c:/Users/Admin/Desktop/crawler/scripts/evaluate_baselines.py): E9 Baseline suite evaluation.

---

## 2. Core Claims & Experimental Design

The evaluation is structured around 4 core claims:

| ID | Claim | Owned by | Key Finding |
| :-- | :--- | :--- | :--- |
| **C1** | Per-relation world-assumption routing dominates fixed CWA and fixed OWA on KGs with heterogeneous relation density. | E2, E3 | Macro-F1 improves on heterogeneous catalog (RMIT) while lowering False Contradiction Rate (FCR). |
| **C2** | Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI. | E4, E5 | 5-fold cross-fitted Meta-Confidence yields significant $\Delta\text{AURC}$ gains. |
| **C3** | Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; tri-state protocols can. | E6, E7 | Phase 0 diagnostic (E0.1) confirmed CoDEx/MetaQA label priors decouple prediction from graph triples ($\Delta < 5$ pts). |
| **C4** | Post-hoc claim-level verification is deployable on closed institutional catalogs with controlled false-contradictions. | E8, E9 | E2E domain accuracy reaches **95.00%** on RMIT ($n=300$) and **92.50%** on Catalog2 ($n=200$). |

---

## 3. Linking Axes & Baseline Benchmark Summary

Evaluating performance across explicit linking condition axes (**L0**: Gold IDs injected, **L1**: Bi-encoder retrieval, **L2**: Heuristic string overlap):

| Model / Engine | Dataset | Evaluated ($n$) | Linking Axis | E2E Accuracy | 95% Confidence Interval | Coverage | Selective Accuracy |
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

*Note on FEVER*: Excluded from structured verification runs (`N/A (unstructured text evidence, not triples)`).


---

## 4. Execution Guidelines & Commands

Execute evaluation scripts using local virtual environment Python:

```powershell
# Run Phase 0 Diagnostics
& .venv\Scripts\python.exe scripts/run_phase0_diagnostics.py

# Generate Offline Completeness Profiles
& .venv\Scripts\python.exe scripts/generate_completeness_profiles.py

# Generate Tri-State Benchmarks
& .venv\Scripts\python.exe scripts/generate_tristate_benchmarks.py

# Run Revised Experiments (E2-E5)
& .venv\Scripts\python.exe scripts/run_revised_experiments.py

# Quantify Binary Trap (E7)
& .venv\Scripts\python.exe scripts/evaluate_binary_trap.py

# Run Baseline Suite (E9)
& .venv\Scripts\python.exe scripts/evaluate_baselines.py
```
