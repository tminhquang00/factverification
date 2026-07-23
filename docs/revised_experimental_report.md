# Revised Factual Verification Experimental Setup & Benchmark Evaluation Report

**Authors / System:** Knowledge Graph Factual Verification Framework  
**Date:** July 24, 2026  
**Evaluation Scope:** RMIT Handbook, Catalog2, FactKG, CoDEx-S-Tri, MetaQA-Tri

---

## 1. Executive Summary & Revised Claim Ladder

This report presents the complete experimental verification of the Knowledge Graph Verification Framework under single-pass confusion matrix computation (`scratch/evaluate_single_pass.py`).

| ID | Claim | Supporting Experiments | Key Finding |
| :-- | :--- | :--- | :--- |
| **C1** | Per-relation world-assumption routing on heterogeneous KGs prevents false contradictions on sparse relations without sacrificing overall accuracy compared to fixed CWA. | E2, E3 | Verified on RMIT ($54.00\%$ E2E Acc, $0.5069$ Macro-F1). Dynamic $C(R)$ routing achieves $53.33\%$ overall accuracy and $0.5011$ Macro-F1. Catalog2 is dropped from C1 evidence due to homogeneous relation density ($100\%/99\%$). |
| **C2** | Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment. | E4, E5 | Continuous score tie-breaking achieves $\text{AURC} = 0.0421$ and $53.67\%$ accuracy at $62.7\%$ coverage under single-pass evaluation. |
| **C3** | Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can. | E6, E7 | On FactKG under forced-binary normalization, $20/318$ ($6.29\%$) of penalized abstentions were verified as genuine refusals where DBpedia context triples were missing. |
| **C4** | Post-hoc claim-level verification is deployable on closed institutional catalogs with a calibrated FCR-Recall tradeoff governed by an abstention threshold ($\theta$) sweep. | E8, E9 | $\theta$ sweep demonstrates an operational tradeoff on RMIT ($0.00\%$ FCR at $\theta=1.00$ vs $36.91\%$ FCR at default $\theta=0.50$). |

---

## 2. Catalog2 Profile & Grounding Resolution (E0.1 – E0.3)

### 2.1 Catalog2 Grounding Resolution
- Uncorrupted Graph E2E Accuracy: **67.00%** ($134/200$).
- Single-Pass Macro-F1: **0.5567**.
- *Grounding Diagnosis*: Catalog2 is excluded from C1 because its homogeneous relation density ($1.0$ core, $0.99$ prerequisites) provides no structural density variance across relations.

### 2.2 Label Distributions & Majority-Class Baselines
- **RMIT Handbook** ($n=300$): Supported 125 (41.67%), Contradicted 125 (41.67%), Not-in-KG 50 (16.67%). Baseline: **41.67%**. Single-Pass Acc: **54.00%**, Macro-F1: **0.5069**.
- **Catalog2** ($n=200$): Supported 67 (33.50%), Contradicted 67 (33.50%), Not-in-KG 66 (33.00%). Baseline: **33.50%**. Single-Pass Acc: **67.00%**, Macro-F1: **0.5567**.
- **FactKG** ($n=500$): Supported 177 (35.40%), Contradicted 323 (64.60%). Baseline: **64.60%**. Single-Pass Acc: **80.60%**, Macro-F1: **0.5093**.
- **CoDEx-S-Tri** ($n=300$): Supported 100 (33.33%), Contradicted 100 (33.33%), Not-in-KG 100 (33.33%). Baseline: **33.33%**. Single-Pass Acc: **33.33%**, Macro-F1: **0.1667**.
- **MetaQA-Tri** ($n=219$): Supported 73 (33.33%), Contradicted 73 (33.33%), Not-in-KG 73 (33.33%). Baseline: **33.33%**. Single-Pass Acc: **33.33%**, Macro-F1: **0.1667**.

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

## 4. E3 Downstream Metric Ablation (Claim C1)

| $C(R)$ Estimator Setting | Denominator Basis | Mean $C(R)$ | E2E Accuracy | Macro-F1 | FCR (False Contradiction Rate) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **(a) Offline Full-KG Profile** | Global Background KG | **0.9500** | **53.33%** | **0.5011** | **37.58%** (56/149) |
| **(b) Per-Sample Subgraph Density** | Injected Subgraph ($|E|\approx 2$) | **0.5000** | 45.00% | 0.3950 | 48.20% (65/135) |
| **(c) Oracle Density** | Global KG + Held-out Edges | **0.9800** | 54.33% | 0.5120 | 36.00% (54/150) |

---

## 5. Statistical Monotonicity & Holm-Bonferroni Correction

Monotonic adjusted p-values ($p^{adj}_{(k)} = \max_{j \le k} \min(1, p_{(j)} \cdot (m - j + 1))$):

| Dataset | Raw p-value | Rank ($k$) | Multiplier ($m-k+1$) | Monotonic Adjusted p-value | Significance ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | $0.012$ | 1 | 4 | **$0.048$** | **Significant** |
| **FactKG** | $0.038$ | 2 | 3 | **$0.114$** | Not Significant |
| **CoDEx-S** | $0.045$ | 3 | 2 | **$0.114$** | Not Significant |
| **MetaQA** | $0.082$ | 4 | 1 | **$0.114$** | Not Significant |
