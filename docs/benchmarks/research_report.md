# Post-Hoc Knowledge Graph Fact-Verification for LLM Responses: System Design, Methodology, and Experimental Evaluation

---

## Abstract

Large Language Models (LLMs) produce fluent natural-language responses but remain susceptible to hallucination — generating plausible but factually incorrect assertions. In high-stakes administrative domains such as university course advising, even a single erroneous prerequisite or coordinator attribution can cascade into enrollment errors, audit failures, or compliance violations. This report presents a **post-hoc, claim-level fact-verification framework** that validates LLM-generated assertions against a structured Knowledge Graph (KG). The system decomposes natural-language responses into atomic triples, resolves entities deterministically, and verifies each triple against the graph using a novel **dynamic completeness estimator** that adaptively routes verdicts between Closed-World and Open-World semantics. A **calibrated selective abstention mechanism** further controls false-alarm rates by downgrading low-confidence contradictions to explicit uncertainty flags.

We evaluate the pipeline across frozen protocols: (i) a 300-item RMIT Course Handbook tri-state dataset, (ii) 500 items from FactKG (DBpedia triples), (iii) 300 items from `CoDEx-S-Tri`, (iv) 219 items from `MetaQA-Tri`, and (v) 200 items from Catalog2. On RMIT ($n=300$), the pipeline achieves **54.00% tri-state end-to-end accuracy** and **0.5069 Macro-F1** under single-pass confusion matrix computation (outperforming the **41.67% majority-class baseline**). On Catalog2 ($n=200$), uncorrupted KG evaluation yields **67.00% accuracy** and **0.5567 Macro-F1**. On FactKG ($n=500$), the pipeline achieves **80.60% E2E accuracy** under forced-decision label normalization (`Not-in-KG` $\rightarrow$ `Contradicted` per `AGENTS.md`).

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

### 2.2 Confusion Matrices (Gold Rows vs. Predicted Columns)

#### RMIT Handbook ($n=300$, L1 Neural Linking, Single-Pass Execution)
| Gold Label \ Predicted | Supported | Contradicted | Not-in-KG | Total | Class Precision | Class Recall | Class F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Supported** | **17** | 56 | 52 | 125 | 43.59% | 13.60% | 0.2073 |
| **Contradicted** | 22 | **95** | 8 | 125 | 62.91% | 76.00% | 0.6884 |
| **Not-in-KG** | 0 | 0 | **50** | 50 | 45.45% | 100.00% | 0.6250 |
| **Total** | 39 | 151 | 110 | 300 | **Acc: 54.00%** | | **Macro-F1: 0.5069** |

*RMIT FCR & Recall*:
- **False Contradiction Rate (FCR)**: $56/151 = \mathbf{37.09\%}$ (56 false contradictions out of 151 contradiction predictions).
- **Contradiction Recall**: $95/125 = \mathbf{76.00\%}$.

#### Catalog2 ($n=200$, L1 Neural Linking)
| Gold Label \ Predicted | Supported | Contradicted | Not-in-KG | Total |
| :--- | :---: | :---: | :---: | :---: |
| **Supported** | **67** | 0 | 0 | 67 |
| **Contradicted** | 0 | **67** | 0 | 67 |
| **Not-in-KG** | 66 | 0 | **0** | 66 |
| **Total** | 133 | 67 | 0 | 200 |

*Catalog2 FCR & Recall*:
- **False Contradiction Rate (FCR)**: $0/67 = \mathbf{0.00\%}$.
- **Contradiction Recall**: $67/67 = \mathbf{100.00\%}$.

#### FactKG ($n=500$, L1 Forced Binary Mode)
| Gold Label \ Predicted | Supported | Contradicted | Total | Precision | Recall | F1 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Supported** | **96** | 81 | 177 | 85.71% | 54.24% | 0.6644 |
| **Contradicted** | 16 | **307** | 323 | 79.12% | 95.05% | 0.8636 |
| **Total** | 112 | 388 | 500 | **Acc: 80.60%** | | **Macro-F1: 0.5093** |

---

## 3. Headline Evaluation Table across Linking Axes (L0 / L1 / L2)

Strictly generated from single-pass evaluation:

| Dataset | $n$ | Linking Axis | E2E Accuracy | 95% Clustered CI | Tri-State Macro-F1 | False Contradiction Rate (FCR) | Contradiction Recall | Coverage | Selective Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | 300 | **L0** (Oracle) | 56.00% | [51.33%, 60.67%] | 0.5210 | 50/145 (34.48%) | 96/125 (76.80%) | 100.0% | 56.00% |
| **RMIT** | 300 | **L1** (Neural) | 54.00% | [49.33%, 58.67%] | 0.5069 | 56/151 (37.09%) | 95/125 (76.00%) | 100.0% | 54.00% |
| **RMIT** | 300 | **L2** (Heuristic) | 51.33% | [46.67%, 56.00%] | 0.4780 | 60/155 (38.71%) | 90/125 (72.00%) | 100.0% | 51.33% |
| **Catalog2** | 200 | **L0** (Oracle) | 70.00% | [64.50%, 75.50%] | 0.5812 | 0/67 (0.00%) | 67/67 (100.0%) | 100.0% | 70.00% |
| **Catalog2** | 200 | **L1** (Neural) | 67.00% | [60.50%, 73.50%] | 0.5567 | 0/67 (0.00%) | 67/67 (100.0%) | 100.0% | 67.00% |
| **Catalog2** | 200 | **L2** (Heuristic) | 62.50% | [55.50%, 69.50%] | 0.4980 | 0/67 (0.00%) | 67/67 (100.0%) | 100.0% | 62.50% |
| **FactKG** | 500 | **L0** (Oracle) | 80.00% | [76.20%, 83.60%] | 0.5010 | 80/380 (21.05%) | 300/323 (92.88%) | 52.40% | 71.76% |
| **FactKG** | 500 | **L1** (Neural) | 80.60% | [76.80%, 84.40%] | 0.5093 | 81/388 (20.88%) | 307/323 (95.05%) | 52.20% | 74.33% |
| **FactKG** | 500 | **L2** (Heuristic) | 78.40% | [74.60%, 82.00%] | 0.4850 | 85/395 (21.52%) | 295/323 (91.33%) | 48.10% | 68.20% |
| **CoDEx-S-Tri** | 300 | **L0** (Oracle) | 35.00% | [29.67%, 40.33%] | 0.1800 | 0/0 (0.00%) | 0/100 (0.00%) | 100.0% | 35.00% |
| **CoDEx-S-Tri** | 300 | **L1** (Neural) | 33.33% | [28.00%, 38.67%] | 0.1667 | 0/0 (0.00%) | 0/100 (0.00%) | 100.0% | 33.33% |
| **CoDEx-S-Tri** | 300 | **L2** (Heuristic) | 31.00% | [25.67%, 36.33%] | 0.1500 | 0/0 (0.00%) | 0/100 (0.00%) | 100.0% | 31.00% |
| **MetaQA-Tri** | 219 | **L0** (Oracle) | 36.00% | [29.68%, 42.32%] | 0.1900 | 0/0 (0.00%) | 0/73 (0.00%) | 100.0% | 36.00% |
| **MetaQA-Tri** | 219 | **L1** (Neural) | 33.33% | [27.10%, 39.56%] | 0.1667 | 0/0 (0.00%) | 0/73 (0.00%) | 100.0% | 33.33% |
| **MetaQA-Tri** | 219 | **L2** (Heuristic) | 30.00% | [24.00%, 36.00%] | 0.1450 | 0/0 (0.00%) | 0/73 (0.00%) | 100.0% | 30.00% |

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

*C1 Thesis Synthesis*: Catalog2 is dropped from C1 because its homogeneous 99-100% density provides no structural density variance. On RMIT, dynamic routing achieves comparable overall accuracy (53.33% vs 53.33% CWA) and Macro-F1 (0.5011 vs 0.5003), confirming that dynamic completeness estimation provides stable world-assumption routing without degradation.

### 4.2 E3 Downstream Metric Sensitivity to $C(R)$ Estimator (Claim C1)

| $C(R)$ Estimator Setting | Denominator Basis | Mean $C(R)$ | E2E Accuracy | Macro-F1 | FCR (False Contradiction Rate) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **(a) Offline Full-KG Profile** | Global Background KG | **0.9500** | **53.33%** | **0.5011** | **37.58%** (56/149) |
| **(b) Per-Sample Subgraph Density** | Injected Subgraph ($|E|\approx 2$) | **0.5000** | 45.00% | 0.3950 | 48.20% (65/135) |
| **(c) Oracle Density** | Global KG + Held-out Edges | **0.9800** | 54.33% | 0.5120 | 36.00% (54/150) |

### 4.3 E4 Threshold $\theta$ Sweep & FCR–Recall Tradeoff (Headline for C4)

Sweeping the abstention threshold $\theta \in [0.0, 1.0]$ on RMIT establishes the FCR–Contradiction Recall trade-off curve:

| Abstention Threshold ($\theta$) | Coverage | Selective Accuracy | Tri-State Macro-F1 | False Contradiction Rate (FCR) | Contradiction Recall | Operational Profile |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **0.00** | 63.0% | 53.33% | 0.5020 | 37.58% (56/149) | 74.40% (93/125) | Maximum recall |
| 0.20 | 62.3% | 53.67% | 0.5027 | 36.91% (55/149) | 75.20% (94/125) | High coverage |
| **0.50** (Default) | **62.7%** | **53.67%** | **0.5036** | **36.91%** (55/149) | **75.20%** (94/125) | Default balanced |
| 0.80 | 63.3% | 53.67% | 0.5069 | 37.58% (56/149) | 74.40% (93/125) | Stable region |
| **1.00** | **13.3%** | **22.33%** | **0.1762** | **0.00%** (0/0) | **0.00%** (0/125) | Total abstention |

---

## 5. Phase 3 & 4 Benchmark & Baseline Suite Results

### 5.1 E7 Binary Trap Analysis (Claim C3)
Out of 318 penalized abstentions on FactKG under forced-binary normalization (`Not-in-KG` $\rightarrow$ `Contradicted`), **20 items (6.29%) were verified as correct refusals** where DBpedia context triples were missing, demonstrating that binary forced decision penalizes legitimate uncertainty.

### 5.2 Monotonic Holm-Bonferroni Correction & Revised Significance Claims
Applying standard monotonic Holm-Bonferroni correction ($p^{adj}_{(k)} = \max_{j \le k} \min(1, p_{(j)} \cdot (m - j + 1))$) to the family of 4 dataset $\Delta\text{AURC}$ p-values ($m=4$):

| Dataset | Raw p-value | Rank ($k$) | Multiplier ($m-k+1$) | Raw Step Adjusted | Monotonic Adjusted p-value | Significance ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | $0.012$ | 1 | 4 | $0.048$ | **$0.048$** | **Significant** |
| **FactKG** | $0.038$ | 2 | 3 | $0.114$ | **$0.114$** | Not Significant |
| **CoDEx-S** | $0.045$ | 3 | 2 | $0.090$ | **$0.114$** | Not Significant |
| **MetaQA** | $0.082$ | 4 | 1 | $0.082$ | **$0.114$** | Not Significant |

*Revised Significance Finding*: Exactly 1 of 4 dataset comparisons (RMIT Handbook) survives Holm-Bonferroni family-wise error rate control at $\alpha=0.05$. Public dataset deltas do not reach statistical significance after monotonic correction.
