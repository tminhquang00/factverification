# Knowledge Graph Verification Framework - Documentation

Welcome to the documentation suite for the **Knowledge Graph (KG) Fact-Verification & Calibration Framework**. This directory contains architectural specifications, benchmark analysis, calibration reports, and reproduction walkthroughs.

---

## 📁 Directory Structure & Index

### 🏛️ 1. Architecture & Design (`docs/architecture/`)
Comprehensive documentation of the framework architecture, algorithms, and pipeline stages:

* **[design.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/design.md)**: System Architecture Specification, 4-Stage Tri-State Pipeline, Graph Completeness Estimator $C(R)$, and Selective Abstention.
* **[system_expert_review.md](file:///c:/Users/Admin/Desktop/crawler/docs/architecture/system_expert_review.md)**: Algorithm-level technical breakdown for domain experts, including mathematical definitions for dynamic relation completeness and entity linking routines.

---

### 📊 2. Benchmarks & Evaluation (`docs/benchmarks/` and `docs/`)
Empirical research findings across university handbooks, institutional catalogs, and public benchmark datasets (`FactKG`, `CoDEx-S-Tri`, `MetaQA-Tri`):

* **[revised_experimental_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/revised_experimental_report.md)**: Master evaluation report under the revised experimental setup migration plan across Claims C1–C4, Phase 0 Diagnostics, and Linking Axes (L0/L1/L2).
* **[research_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report.md)**: Complete benchmark report including multi-model evaluations, 95% Bootstrap Confidence Intervals, Selective Accuracy, Coverage metrics, and ablation studies.
* **[calibration_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/calibration_report.md)**: Analysis of tri-state decision calibration, selective abstention threshold sweeps, and risk-coverage curves.

---

### 📋 3. Revised Claim Ladder & Primary Findings

| Claim ID | Headline Finding | Core Supporting Evidence |
| :--- | :--- | :--- |
| **C1** | Per-relation world-assumption routing dominates fixed CWA & OWA on KGs with heterogeneous relation density. | E2 Routing Ablation: Tri-State Macro-F1 $0.2305$ vs $0.2257$ (Fixed CWA); False Contradiction Rate $6.67\%$ vs $15.63\%$ (Fixed CWA). |
| **C2** | Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment. | E4/E5 Sweeps: Continuous score tie-breaking resolves mass ties ($2\%$ tie fraction); AURC $= 0.0421$, Selective Acc $= 91.00\%$ @ $75\%$ coverage. |
| **C3** | Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can. | E6/E7 Benchmark Trap: Quantified that $8.13\%$ of penalized abstentions on FactKG were correct refusals due to missing KG groundings. |
| **C4** | Post-hoc claim-level verification is deployable on closed institutional catalogs with controlled false-contradiction rates. | E8/E9 Institutional Catalog: Verified on RMIT ($94.67\%$) and Catalog2 ($88.00\%$ E2E Acc, $0.00\%$ FCR), outperforming closed-book LLMs. |

---

### 🏆 4. Multi-Dataset Evaluation Summary Across Linking Axes

| Dataset | Sample Size ($n$) | Reporting Axis | E2E Accuracy | 95% Clustered CI | Tri-State Macro-F1 | False Contradiction Rate (FCR) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT Handbook** | 300 | **L1** (Neural) | **94.67%** | [92.00%, 97.00%] | **0.2305** | **6.67%** |
| **Catalog2** | 200 | **L1** (Neural) | **88.00%** | [83.00%, 92.50%] | **0.5465** | **0.00%** |
| **FactKG** | 500 | **L1** (Forced Binary) | **81.00%** | [77.40%, 84.40%] | **0.1381** | **90.21%** |
| **CoDEx-S-Tri** | 300 | **L1** (Neural) | **37.20%** | [31.80%, 40.40%] | **0.3580** | **0.00%** |
| **MetaQA-Tri** | 219 | **L1** (Neural) | **48.00%** | [39.73%, 53.42%] | **0.4658** | **0.00%** |
