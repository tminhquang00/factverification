# Post-Hoc Knowledge Graph Fact-Verification for LLM Responses: System Design, Methodology, and Experimental Evaluation

---

## Abstract

Large Language Models (LLMs) produce fluent natural-language responses but remain susceptible to hallucination — generating plausible but factually incorrect assertions. In high-stakes administrative domains such as university course advising, even a single erroneous prerequisite or coordinator attribution can cascade into enrollment errors, audit failures, or compliance violations. This report presents a **post-hoc, claim-level fact-verification framework** that validates LLM-generated assertions against a structured Knowledge Graph (KG). The system decomposes natural-language responses into atomic triples, resolves entities deterministically, and verifies each triple against the graph using a novel **dynamic completeness estimator** that adaptively routes verdicts between Closed-World and Open-World semantics. A **calibrated selective abstention mechanism** further controls false-alarm rates by downgrading low-confidence contradictions to explicit uncertainty flags.

We evaluate the pipeline across frozen protocols and multiple LLM backends: (i) a 300-item RMIT Course Handbook tri-state dataset, (ii) 500 items from FactKG (DBpedia triples), (iii) 300 items from `CoDEx-S-Tri`, (iv) 219 items from `MetaQA-Tri`, and (v) 200 items from Catalog2. Under local LLM execution, single-pass evaluation yields **54.00% tri-state accuracy** on RMIT ($n=300$). Under Azure OpenAI backends (`azure-4.1-mini`, `azure-5-mini`, `azure-4.1`), Catalog2 achieves up to **67.00% accuracy** and **100.0% contradiction recall**, while FactKG reaches **66.40% accuracy** with **99.38% contradiction recall**.

---

## 1. Core Claim Ladder & Catalog2 Dataset Profile

### 1.1 Claim Ladder

The evaluation structure is organized around four core claims:

*   **C1 (World-Assumption Routing)**: Per-relation world-assumption routing on heterogeneous KGs prevents false contradictions on sparse relations without sacrificing overall accuracy compared to fixed CWA.
*   **C2 (Selective Signal Integration)**: Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment.
*   **C3 (Tri-State Protocol Utility)**: Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can.
*   **C4 (Calibrated FCR-Recall Tradeoff)**: Post-hoc claim-level verification is deployable on closed institutional catalogs with a strictly controlled False Contradiction Rate (FCR) governed by an abstention threshold ($\theta$) sweep.

### 1.2 Catalog2 Dataset Profile & Grounding Resolution
- **Source**: Synthetic closed institutional course catalog modeled after RMIT handbook schema conventions.
- **Entity Nodes**: 100 course entity nodes (`MED101` through `MED200`).
- **Relation Classes**: 5 relation types (`name`, `credits`, `offered_terms`, `prerequisites`, `taught_by`).
- **Density Profile**: Homogeneous relation density ($1.0$ for core attributes, $0.99$ for prerequisites).
- **Grounding Resolution**:
  - Uncorrupted Graph Accuracy: **67.00%** ($134/200$).
  - Macro-F1: **0.5567**.
  - *Finding*: Catalog2 is excluded from C1 evidence because its homogeneous relation density offers no structural variance for world-assumption routing.

---

## 2. Single-Pass Label Distributions, Confusion Matrices & Baselines

All metrics are computed in a single pass directly from the 3x3 confusion matrix:

### 2.1 Label Distribution & Majority Class Summary

| Dataset | Total ($n$) | Supported | Contradicted | Not-in-KG | Majority Class Baseline | Single-Pass Acc | Single-Pass Macro-F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT Handbook** | 300 | 125 (41.67%) | 125 (41.67%) | 50 (16.67%) | **41.67%** | **54.00%** | **0.5069** |
| **Catalog2** | 200 | 67 (33.50%) | 67 (33.50%) | 66 (33.00%) | **33.50%** | **67.00%** | **0.5567** |
| **FactKG** | 500 | 177 (35.40%) | 323 (64.60%) | 0 (0.00%) | **64.60%** | **80.60%** | **0.5093** |
| **CoDEx-S-Tri** | 300 | 100 (33.33%) | 100 (33.33%) | 100 (33.33%) | **33.33%** | **33.33%** | **0.1667** |
| **MetaQA-Tri** | 219 | 73 (33.33%) | 73 (33.33%) | 73 (33.33%) | **33.33%** | **33.33%** | **0.1667** |

---

## 3. Headline Multi-Model Evaluation across Azure OpenAI Deployments

Multi-model evaluation across **`azure-4.1-mini`**, **`azure-5-mini`**, and **`azure-4.1`**:

| Model Deployment | Dataset | $n$ | E2E Accuracy | Tri-State Macro-F1 | False Contradiction Rate (FCR) | Contradiction Recall |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`azure-4.1-mini`** | RMIT Handbook | 300 | 25.67% | 0.2201 | 8/34 (23.53%) | 20.80% |
| | Catalog2 | 200 | 65.00% | 0.5476 | **0/67 (0.00%)** | **100.00%** |
| | FactKG | 500 | 66.20% | 0.2991 | 167/488 (34.22%) | **99.38%** |
| | CoDEx-S-Tri | 300 | 34.33% | 0.2260 | 5/6 (83.33%) | 1.00% |
| | MetaQA-Tri | 219 | 36.53% | 0.3066 | **0/9 (0.00%)** | 12.33% |
| **`azure-5-mini`** | RMIT Handbook | 300 | 26.67% | 0.2280 | 12/42 (28.57%) | 24.00% |
| | Catalog2 | 200 | **67.00%** | **0.5567** | **0/67 (0.00%)** | **100.00%** |
| | FactKG | 500 | 64.80% | 0.2824 | 171/489 (34.97%) | **98.45%** |
| | CoDEx-S-Tri | 300 | 34.33% | 0.2298 | 5/6 (83.33%) | 1.00% |
| | MetaQA-Tri | 219 | **37.90%** | **0.3582** | **0/13 (0.00%)** | 17.81% |
| **`azure-4.1`** | RMIT Handbook | 300 | 26.33% | 0.2227 | 17/46 (36.96%) | 23.20% |
| | Catalog2 | 200 | 66.50% | 0.5544 | **0/67 (0.00%)** | **100.00%** |
| | FactKG | 500 | 66.40% | 0.3028 | 166/487 (34.09%) | **99.38%** |
| | CoDEx-S-Tri | 300 | 34.33% | 0.2298 | 5/6 (83.33%) | 1.00% |
| | MetaQA-Tri | 219 | 35.16% | 0.2728 | **0/5 (0.00%)** | 6.85% |

---

## 4. Phase 2 Core Claim Results & Downstream Ablations

### 4.1 E2 Stratified World-Assumption Routing Rerun on RMIT (Claim C1)

Stratified by relation density (Dense `hasCreditValue` vs. Sparse `taughtBy` / `requiresPrerequisite`):

| Relation Density Stratum | Routing Mode | E2E Accuracy | Tri-State Macro-F1 | False Contradiction Rate (FCR) | Contradiction Recall |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Sparse Relations** | **Dynamic $C(R)$** | **42.86%** | **0.2203** | **40.94%** (52/127) | **75.00%** (75/100) |
| | Fixed CWA | 42.86% | 0.2203 | 40.94% (52/127) | 75.00% (75/100) |
| | Fixed OWA | 42.86% | 0.2203 | 40.94% (52/127) | 75.00% (75/100) |
| **Overall RMIT** | **Dynamic $C(R)$** | **53.33%** | **0.5011** | **37.58%** (56/149) | **74.40%** (93/125) |
| | Fixed CWA | 53.33% | 0.5003 | 36.73% (54/147) | 74.40% (93/125) |
| | Fixed OWA | 53.00% | 0.4974 | 37.84% (56/148) | 73.60% (92/125) |

### 4.2 Monotonic Holm-Bonferroni Correction & Revised Significance Claims
Applying standard monotonic Holm-Bonferroni correction ($p^{adj}_{(k)} = \max_{j \le k} \min(1, p_{(j)} \cdot (m - j + 1))$) to the family of 4 dataset $\Delta\text{AURC}$ p-values ($m=4$):

| Dataset | Raw p-value | Rank ($k$) | Multiplier ($m-k+1$) | Raw Step Adjusted | Monotonic Adjusted p-value | Significance ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | $0.012$ | 1 | 4 | $0.048$ | **$0.048$** | **Significant** |
| **FactKG** | $0.038$ | 2 | 3 | $0.114$ | **$0.114$** | Not Significant |
| **CoDEx-S** | $0.045$ | 3 | 2 | $0.090$ | **$0.114$** | Not Significant |
| **MetaQA** | $0.082$ | 4 | 1 | $0.082$ | **$0.114$** | Not Significant |
