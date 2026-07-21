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

* **[research_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report.md)**: Complete benchmark report including 95% Bootstrap Confidence Intervals, Selective Accuracy, Coverage metrics, and ablation studies.
* **[calibration_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/calibration_report.md)**: Analysis of tri-state decision calibration, selective abstention threshold sweeps, and risk-coverage curves.
* **[research_report_v2.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report_v2.md)**: Comparative analysis of baseline variations and early pipeline iterations.

---

### 🖼️ 3. Visual Assets (`docs/assets/`)
Figures, plots, and visualizations referenced in research reports:

* **`docs/assets/risk_coverage_curves.png`**: Risk vs Coverage curves across confidence estimation methods.
* **`docs/assets/score_distributions.png`**: Confidence score distribution plots for covered vs abstained claims.

---

### 🚀 4. Walkthrough & Implementation (`docs/`)

* **[walkthrough.md](file:///c:/Users/Admin/Desktop/crawler/docs/walkthrough.md)**: Step-by-step guide for executing evaluations, running RMIT handbook verification, and reproducing benchmark figures.
* **[implementation_plan.md](file:///c:/Users/Admin/Desktop/crawler/docs/implementation_plan.md)**: Technical implementation plan and development roadmap.
