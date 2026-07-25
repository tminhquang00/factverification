# Knowledge Graph Verification Framework - Documentation

Welcome to the documentation suite for the **Knowledge Graph (KG) Fact-Verification & Calibration Framework**. This directory contains architectural specifications, benchmark analysis, calibration reports, and reproduction walkthroughs.

## Research Roadmap

* **[research_improvement_plan.md](research_improvement_plan.md)**: Evidence-grounded review of the current implementation and a staged plan for rebuilding the study around set-valued answer completeness, calibrated dual-risk deferral, and valid graph-groundedness controls.
* **[experiment_registry.md](experiment_registry.md)**: Authoritative validity status for existing scripts, reports, and result artifacts.
* **[implementation_status.md](implementation_status.md)**: Completed implementation work, candidate artifacts, current limits, and the next executable steps.
* **[advisor_audit_protocol.md](advisor_audit_protocol.md)**: Source-grounded instructions for the selected single-reviewer RMIT expected-set audit.
* **[experiment_runbook.md](experiment_runbook.md)**: Exact PowerShell commands for RMIT, FactKG, and CoDEx experiments, including all saved output paths.

> [!CAUTION]
> Historical benchmark tables below are retained for traceability but are invalidated and must not be cited as research results.

---

## 📁 Directory Structure & Index

### 🏛️ 1. Architecture & Design (`docs/architecture/`)
Comprehensive documentation of the framework architecture, algorithms, and pipeline stages:

* **[design.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/design.md)**: System Architecture Specification, 4-Stage Tri-State Pipeline, Graph Completeness Estimator $C(R)$, and Selective Abstention.
* **[system_expert_review.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/system_expert_review.md)**: Algorithm-level technical breakdown for domain experts, including mathematical definitions for dynamic relation completeness and entity linking routines.
* **[system_explained_v3.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/system_explained_v3.md)**: Version 3 complete pipeline overview with detailed state machine flows.

---

### 📊 2. Benchmarks & Evaluation (`docs/benchmarks/`)
Empirical research findings across university handbook and public benchmark datasets (`FactKG`, `CoDEx`, `MetaQA`, `FEVER`):

* **[comprehensive_report_20260725.md](benchmarks/comprehensive_report_20260725.md)**: **Independent review of the current study (2026-07-25).** Recomputes every headline figure from row-level artifacts, then adds four new diagnostics: the CoDEx `Supported` collapse is an object-namespace bug rather than an entity-linking failure; the LLM verification path is *not* graph-grounded on CoDEx (2–3% prediction change under full content destruction); the FactKG prefix sample covers only 2 of 13 reasoning types; and CoDEx `Not-in-KG` is forfeited by an entity linker with no rejection threshold. Carries corrections to the paper below.
* **[rerun_20260725_paper.md](benchmarks/rerun_20260725_paper.md)**: **Authoritative current study (2026-07-25).** Full paper — data provenance, system description, methodology, defect analysis, results, run-to-run reliability, threats to validity, and an explicit statement of what may and may not be claimed. All aggregates are recomputed from row-level predictions.
* **[rerun_20260725_report.md](benchmarks/rerun_20260725_report.md)**: Chronological run log for the same study (pre-fix sweep, repair, post-fix sweep). Carries no results tables.
* **[research_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report.md)**: *(invalidated)* Historical benchmark report including multi-model evaluations, bootstrap CIs, selective accuracy, coverage, and ablation studies.
* **[calibration_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/calibration_report.md)**: *(invalidated)* Historical analysis of tri-state decision calibration, abstention threshold sweeps, and risk-coverage curves.

---

### 🖼️ 3. Visual Assets (`docs/assets/`)
Figures, plots, and visualizations referenced in research reports:

* **`docs/assets/risk_coverage_curves.png`**: Risk vs Coverage curves across confidence estimation methods.
* **`docs/assets/score_distributions.png`**: Confidence score distribution plots for covered vs abstained claims.

---

---

### 🏆 5. Current Study — 2026-07-25 (`rerun_20260725_fixed`)

Full paper: **[benchmarks/rerun_20260725_paper.md](benchmarks/rerun_20260725_paper.md)**.
Post-fix results, recomputed from row-level predictions via `scripts/summarize_rerun_results.py`.
Zero crashes in all six cells.

| LLM Engine | Dataset | $n$ | Accuracy | 95% CI (IID rows) | Majority floor | Macro-F1 | Coverage | Selective Acc. |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `azure-4.1-mini` | RMIT | 300 | **97.33%** | [95.33%, 99.00%] | 41.67% | 0.988 | 97.67% | 99.66% |
| `gemma-4-e4b` | RMIT | 300 | **92.33%** | [89.33%, 95.33%] | 41.67% | 0.921 | 97.67% | 94.54% |
| `azure-4.1-mini` | FactKG | 500 | **80.20%** | [76.80%, 83.40%] | 64.60% | 0.777 | 56.60% | 74.56% |
| `gemma-4-e4b` | FactKG | 500 | **79.80%** | [76.20%, 83.20%] | 64.60% | 0.752 | 40.00% | 85.50% |
| `azure-4.1-mini` | CoDEx | 500 | **41.80%** | [37.40%, 46.00%] | 35.80% | 0.345 | 99.60% | 41.77% |
| `gemma-4-e4b` | CoDEx | 500 | **37.20%** | [32.60%, 41.60%] | 35.80% | 0.285 | 89.60% | 37.05% |

Principal findings:

* **A stage-3 defect was inflating FactKG.** `verification_pipeline.py:305` shadowed the `mapped()` helper, crashing 22.6% of FactKG rows under `azure-4.1-mini`; the harness converted 113 crashes into 111 scored-correct predictions. Repaired (suite 23 → 25 tests). The post-fix delta is only −1.2 points, but that is a coincidence of label alignment, not evidence the defect was harmless.
* **CoDEx has lost the `Supported` class**: recall 0.039 (`azure-4.1-mini`) and 0.006 (`gemma-4-e4b`) at precision 1.000. The engines then fail in opposite directions — 67.7% of true-`Supported` rows become `Contradicted` under azure versus 70.3% becoming `Not-in-KG` under gemma — which the headline accuracies hide entirely.
* **Run-to-run nondeterminism flips 2.0–9.6% of predictions** (mean 5.75%) between identical reruns, so single-run gaps below ~2 points are not resolvable.
* **RMIT is engine-sensitive by reasoning type**, on disjoint slices: `gemma-4-e4b` drops to 58.0% on existence, `azure-4.1-mini` to 86.0% on multi-hop.
* **The graph-destruction control reproduces bit-identically**: 100% baseline → 48.5% empty → 57.6% shuffled, all intervals excluding zero.
* **RMIT's absolute accuracy is structurally inflated**: `eval_rmit.py:54` verifies a template string interpolated from the same KG fields the verifier then queries.

---

### 📉 6. Historical Multi-Model Table (invalidated — retained for traceability only)

> [!CAUTION]
> The table below predates the evidence quarantine and must not be cited. See
> [experiment_registry.md](experiment_registry.md).

| LLM Engine | Dataset | Evaluated ($n$) | E2E Accuracy | 95% Confidence Interval | Coverage | Selective Accuracy |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **azure-4.1-mini** | **RMIT Handbook** | 300 | **95.00%** | [92.33%, 97.33%] | 100.00% | **95.00%** |
| **azure-4.1-mini** | **FactKG** | 500 | **81.00%** | [77.40%, 84.40%] | 52.20% | **74.33%** |
| **azure-4.1-mini** | **CoDEx-S** | 500 | **37.20%** | [33.00%, 41.40%] | 100.00% | **37.20%** |
| **azure-4.1-mini** | **MetaQA** | 219 | **37.90%** | [31.50%, 44.30%] | 100.00% | **37.90%** |
| **azure-5-mini** | **FactKG** | 500 | **79.60%** | [75.80%, 83.20%] | 51.80% | **75.68%** |
| **azure-5-mini** | **CoDEx-S** | 500 | **37.60%** | [33.40%, 41.80%] | 100.00% | **37.60%** |
| **azure-5-mini** | **MetaQA** | 219 | **40.64%** | [34.20%, 47.10%] | 100.00% | **40.64%** |
| **gemma-4-e4b** | **FactKG** | 500 | **80.00%** | [76.40%, 83.60%] | 36.00% | **87.22%** |
| **gemma-4-e4b** | **CoDEx-S** | 500 | **36.60%** | [32.40%, 40.80%] | 100.00% | **36.60%** |
| **gemma-4-e4b** | **MetaQA** | 219 | **36.53%** | [30.10%, 43.00%] | 100.00% | **36.53%** |

#### Staged Experiments ($n=500$)
- **Exp 1 (Oracle Upper Bound)**: FactKG **80.00% E2E Accuracy**, **71.76% Selective Accuracy** @ 52.40% Coverage.
- **Exp 2 (Neural Entity/Relation Linking)**: CoDEx-S **37.60% E2E Accuracy** with `SentenceTransformer("all-MiniLM-L6-v2")`.
- **Exp 3 (Multi-Hop Decontextualization)**: MetaQA **37.90% E2E Accuracy** @ 100.00% Coverage.
- **Exp 4 (Continuous Calibration Smoothing)**: FactKG **81.40% E2E Accuracy**, **76.06% Selective Accuracy** @ 51.80% Coverage.
