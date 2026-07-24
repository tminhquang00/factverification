# Post-Hoc Knowledge Graph Fact-Verification for LLM Responses: System Design, Methodology, and Experimental Evaluation

---

## Abstract

Large Language Models (LLMs) produce fluent natural-language responses but remain susceptible to hallucination — generating plausible but factually incorrect assertions. In high-stakes administrative domains such as university course advising, even a single erroneous prerequisite or coordinator attribution can cascade into enrollment errors, audit failures, or compliance violations. This report presents a **post-hoc, claim-level fact-verification framework** that validates LLM-generated assertions against a structured Knowledge Graph (KG). The system decomposes natural-language responses into atomic triples, resolves entities deterministically, and verifies each triple against the graph using a novel **dynamic completeness estimator** that adaptively routes verdicts between Closed-World and Open-World semantics. A **calibrated selective abstention mechanism** further controls false-alarm rates by downgrading low-confidence contradictions to explicit uncertainty flags.

We evaluate the pipeline across frozen protocols and multiple LLM backends: (i) a 300-item RMIT Course Handbook tri-state dataset, (ii) 500 items from FactKG (DBpedia triples), (iii) 300 items from `CoDEx-S-Tri`, (iv) 219 items from `MetaQA-Tri`, and (v) 200 items from Catalog2. Under local LLM execution, single-pass evaluation yields **54.00% tri-state accuracy** on RMIT ($n=300$). Under Azure OpenAI backends (`azure-4.1-mini`, `azure-5-mini`, `azure-4.1`), Catalog2 achieves up to **66.50% accuracy** (95% CI: [60.00%, 73.00%]) with **100.0% contradiction recall** and **0.00% FCR**, while FactKG reaches **67.00% accuracy** (95% CI: [63.00%, 71.00%]) with **99.69% contradiction recall**.

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

## 3. Master Multi-Model Evaluation across Azure OpenAI Deployments

Full Master Experiment Sweep across **`azure-4.1-mini`**, **`azure-5-mini`**, and **`azure-4.1`** with **95% Subject-Clustered Bootstrap Confidence Intervals** (1,000 sampling runs):

| Model Deployment | Dataset | $n$ | E2E Accuracy | 95% Subject-Clustered CI | Tri-State Macro-F1 | False Contradiction Rate (FCR) | Contradiction Recall |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`azure-4.1-mini`** | RMIT Handbook | 300 | 27.33% | [22.33%, 32.67%] | 0.2376 | 12/43 (27.91%) | 24.80% |
| | Catalog2 | 200 | 64.50% | [58.50%, 71.50%] | 0.5453 | **0/67 (0.00%)** | **100.00%** |
| | FactKG | 500 | 64.80% | [60.80%, 68.60%] | 0.2855 | 170/487 (34.91%) | **98.14%** |
| | CoDEx-S-Tri | 300 | 34.00% | [28.33%, 39.33%] | 0.2242 | 5/6 (83.33%) | 1.00% |
| | MetaQA-Tri | 219 | 36.07% | [29.68%, 42.47%] | 0.3022 | **0/8 (0.00%)** | 10.96% |
| **`azure-5-mini`** | RMIT Handbook | 300 | 25.67% | [20.67%, 30.67%] | 0.2163 | 14/41 (34.15%) | 21.60% |
| | Catalog2 | 200 | **66.50%** | [60.00%, 73.50%] | **0.5544** | **0/67 (0.00%)** | **100.00%** |
| | FactKG | 500 | 65.40% | [61.20%, 69.80%] | 0.2842 | 171/492 (34.76%) | **99.38%** |
| | CoDEx-S-Tri | 300 | 34.67% | [28.67%, 40.33%] | 0.2317 | 5/6 (83.33%) | 1.00% |
| | MetaQA-Tri | 219 | **37.90%** | [31.51%, 44.29%] | **0.3582** | **0/13 (0.00%)** | 17.81% |
| **`azure-4.1`** | RMIT Handbook | 300 | 26.33% | [21.67%, 31.33%] | 0.2254 | 9/38 (23.68%) | 23.20% |
| | Catalog2 | 200 | **66.50%** | [60.00%, 73.00%] | **0.5544** | **0/67 (0.00%)** | **100.00%** |
| | FactKG | 500 | **67.00%** | [63.00%, 71.00%] | **0.3107** | 164/486 (33.74%) | **99.69%** |
| | CoDEx-S-Tri | 300 | 34.33% | [29.00%, 40.00%] | 0.2298 | 5/6 (83.33%) | 1.00% |
| | MetaQA-Tri | 219 | 35.16% | [28.77%, 41.55%] | 0.2743 | **0/4 (0.00%)** | 5.48% |

---

## 4. E2 World-Assumption Routing Sweep Across Azure Deployments

Comparing Dynamic $C(R)$ routing against fixed CWA and fixed OWA across Azure model backends:

### 4.1 RMIT Handbook ($n=300$)
- **`azure-4.1-mini`**: Dynamic $C(R)$ achieves **26.33% accuracy** and **0.2277 Macro-F1** with **22.22% FCR** ($8/36$), compared to Fixed CWA (**26.67% accuracy**, **32.56% FCR** $14/43$). Dynamic routing suppresses false contradictions by **10.34 percentage points**.
- **`azure-4.1`**: Dynamic $C(R)$ achieves **26.00% accuracy** and **0.2232 Macro-F1** with **27.03% FCR** ($10/37$), compared to Fixed CWA (**26.67% accuracy**, **30.00% FCR** $12/40$).

### 4.2 FactKG ($n=500$)
- **`azure-4.1`**: Dynamic $C(R)$ achieves **66.80% accuracy** and **0.3100 Macro-F1** with **33.81% FCR** ($164/485$) and **99.38% Contradiction Recall**, matching Fixed CWA (**66.60% accuracy**).

---

## 5. Statistical Monotonicity & Holm-Bonferroni Correction

Applying standard monotonic Holm-Bonferroni correction ($p^{adj}_{(k)} = \max_{j \le k} \min(1, p_{(j)} \cdot (m - j + 1))$) to the family of dataset $\Delta\text{AURC}$ p-values ($m=4$):

| Dataset | Raw p-value | Rank ($k$) | Multiplier ($m-k+1$) | Monotonic Adjusted p-value | Significance ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | $0.012$ | 1 | 4 | **$0.048$** | **Significant** |
| **FactKG** | $0.038$ | 2 | 3 | **$0.114$** | Not Significant |
| **CoDEx-S** | $0.045$ | 3 | 2 | **$0.114$** | Not Significant |
| **MetaQA** | $0.082$ | 4 | 1 | **$0.114$** | Not Significant |
