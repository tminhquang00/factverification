# Knowledge Graph (KG) Fact-Verification Framework

This repository implements an end-to-end, tri-state, claim-level factual verification pipeline. The system validates natural language assertions against a structured local Knowledge Graph (such as a university catalog or DBpedia triple graphs) using local, quantized LLMs.

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
              │  (Synonym-Aware & Isolated Match Index)│
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────┐
              │  Stage 4: Factual Graph Verification   │
              │  (Negations, Path-Checks, Existences)  │
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────────┐
              │    Selective Abstention Calibration    │
              │ (Completeness estimation C(R) vs theta)│
              └────────────────────┬───────────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │  Final Tristate Report │
                      │  (Provenance & Flags)  │
                      └────────────────────────┘
```

1. **Draft Response Generation**: Collects natural language answers from an LLM.
2. **Claim Decomposition (Stage 2)**: Breaks draft responses into atomic factual tuples `(Subject, Relation, Object)`. A double-run extraction agreement step filters out small LLM extraction hallucinations.
3. **Entity Resolution & Relation Mapping (Stage 3)**: Normalizes and links entity strings to database nodes using token overlap matching. Unclassified relations are mapped dynamically to matching KG predicates using synonym resolvers.
4. **Semantic Graph Verification (Stage 4)**: Evaluates triples against logic rules (prerequisites, negation checks, email/coordinator verification, existence checks).
5. **Selective Abstention**: Adjusts verdicts between `Contradicted` and `Not-in-KG` based on the relation density / completeness and selective confidence threshold $\theta$.

---

## 2. Project Directory Structure

* `verification_pipeline.py`: Core implementation of the 4-stage fact-verification pipeline.
* `kg_store.py`: Local thread-safe catalog storage containing graph density estimation and relation lookup logic.
* `eval_rmit.py`: Evaluates pipeline correctness on the RMIT Course Handbook dataset.
* `eval_harness.py`: Benchmark evaluation harness for public datasets. Measures accuracy with **95% Bootstrap Confidence Intervals**, **Coverage (In-Scope Claims)**, and **Selective Accuracy** on covered subsets.
* `adapters/`: Data normalization loaders for `FactKG`, `FEVER`, `CoDEx`, and `MetaQA`.
* `scripts/`: Production evaluation sweeps, fast local testing, and meta-confidence calibration scripts.
* `legacy/`: Version 2 legacy framework files.
* `docs/`: Comprehensive project documentation index ([docs/README.md](file:///c:/Users/Admin/Desktop/crawler/docs/README.md)):
  * `docs/architecture/`: Pipeline design (`design.md`), expert review (`system_expert_review.md`), and system breakdown (`system_explained_v3.md`).
  * `docs/benchmarks/`: Benchmark evaluation results (`research_report.md`), calibration report (`calibration_report.md`), and comparative analysis (`research_report_v2.md`).
  * `docs/assets/`: Figures and plots (`risk_coverage_curves.png`, `score_distributions.png`).
  * `docs/walkthrough.md`: Getting started guide and rerun instructions.

---

## 3. Getting Started

### Installation
Activate the local Python virtual environment:
```powershell
.venv\Scripts\activate
```

Install requirements:
```powershell
pip install -r requirements.txt
```

### Running Verification & Evaluations

* **Quick System Evaluation**:
  ```powershell
  & .venv\Scripts\python.exe scripts\run_quick_eval.py
  ```

* **RMIT Handbook Verification**:
  ```powershell
  & .venv\Scripts\python.exe eval_rmit.py
  ```

* **FactKG Baseline (Context LLM)**:
  ```powershell
  & .venv\Scripts\python.exe eval_harness.py --dataset factkg --method context_llm --limit 200
  ```

* **FactKG Pipeline Verification**:
  ```powershell
  & .venv\Scripts\python.exe eval_harness.py --dataset factkg --method pipeline --limit 200
  ```

---

## 4. Key Benchmarks Summary

* **RMIT Handbook Accuracy**: **93.98%** (100.00% accuracy achieved on existence and coordinator verification).
* **FactKG Pipeline Accuracy**: **66.00% (95% CI: [59.00%, 72.50%])** with **79.00% Coverage** and **83.54% Selective Accuracy** (E2E Accuracy = Coverage * Selective Accuracy).
* **Ablation & Calibration Curves**: Disabling the estimator or sweeping the threshold on binary datasets (like FactKG) yields minor changes due to forced decision mappings. The dynamic completeness estimator and selective abstention are best validated on multi-class tri-state benchmarks (e.g. RMIT, showing **100.00% Accuracy** compared to **75.00%** under naive closed-world or open-world assumptions).
