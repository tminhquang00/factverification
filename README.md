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
  * `docs/rmit_dataset_creation.md`: Complete process guide for creating the RMIT Course Handbook Dataset.
  * `docs/architecture/`: Pipeline design (`design.md`), expert review (`system_expert_review.md`), and system breakdown (`system_explained_v3.md`).
  * `docs/benchmarks/`: Benchmark evaluation results (`research_report.md`) and calibration report (`calibration_report.md`).
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

## 4. Key Benchmarks & Experiments Summary

* **RMIT Handbook Domain Accuracy**: **95.00% (95% CI: [92.33%, 97.33%])** across **300 evaluation samples** (285/300 correct; 100.00% accuracy on one-hop, conjunction, and negation reasoning).
* **Multi-Model Scaled Benchmarks ($n=500$)**:
  * **azure-4.1-mini**: FactKG **81.00% E2E Accuracy** (74.33% Selective Accuracy @ 52.20% Coverage), CoDEx-S **37.20%**, MetaQA **37.90%**.
  * **azure-5-mini**: FactKG **79.60% E2E Accuracy** (75.68% Selective Accuracy @ 51.80% Coverage), CoDEx-S **37.60%**, MetaQA **40.64%**.
  * **google/gemma-4-e4b** (Local LM Studio): FactKG **80.00% E2E Accuracy** (87.22% Selective Accuracy @ 36.00% Coverage), CoDEx-S **36.60%**, MetaQA **36.53%**.
* **Staged Pipeline Experiments ($n=500$)**:
  * **Exp 1 (Oracle Linking Upper Bound)**: FactKG **80.00% E2E Accuracy** (71.76% Selective Accuracy @ 52.40% Coverage; 100% linking precision on direct triples).
  * **Exp 2 (Neural Entity/Relation Linking)**: Bi-encoder vector candidate retrieval (`SentenceTransformer` `all-MiniLM-L6-v2`) on CoDEx-S (**37.60%**).
  * **Exp 3 (Multi-Hop Decontextualization & CoVe)**: Factored sub-claim decomposition resolving intermediate bridge entities on MetaQA (**37.90%**).
  * **Exp 4 (Continuous Score Calibration & Smoothing)**: Continuous sigmoid-smoothed confidence score margins on FactKG (**81.40% E2E Accuracy**, **76.06% Selective Accuracy** @ 51.80% Coverage), eliminating discrete confidence=1.0 mass ties.

