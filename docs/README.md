# Knowledge Graph Verification Framework - Documentation

Welcome to the documentation suite for the **Knowledge Graph (KG) Fact-Verification & Calibration Framework**. This directory contains architectural specifications, benchmark analysis, calibration reports, and reproduction walkthroughs.

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

* **[research_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report.md)**: Complete benchmark report including multi-model evaluations, 95% Bootstrap Confidence Intervals, Selective Accuracy, Coverage metrics, and ablation studies.
* **[calibration_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/calibration_report.md)**: Analysis of tri-state decision calibration, selective abstention threshold sweeps, and risk-coverage curves.

---

### 🖼️ 3. Visual Assets (`docs/assets/`)
Figures, plots, and visualizations referenced in research reports:

* **`docs/assets/risk_coverage_curves.png`**: Risk vs Coverage curves across confidence estimation methods.
* **`docs/assets/score_distributions.png`**: Confidence score distribution plots for covered vs abstained claims.

---

---

### 🏆 5. Latest Multi-Model Benchmark & Staged Experiment Summary ($n=500$)

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
