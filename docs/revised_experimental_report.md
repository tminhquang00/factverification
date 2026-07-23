# Revised Factual Verification Experimental Setup & Benchmark Evaluation Report

**Authors / System:** Knowledge Graph Factual Verification Framework  
**Date:** July 24, 2026  
**Evaluation Scope:** RMIT Handbook, Catalog2, FactKG, CoDEx-S-Tri, MetaQA-Tri  
**LLM Deployments:** Local Gemma-4, `azure-4.1-mini`, `azure-5-mini`, `azure-4.1`

---

## 1. Executive Summary & Revised Claim Ladder

This report presents the complete multi-model experimental verification of the Knowledge Graph Verification Framework across local and Azure OpenAI backends.

| ID | Claim | Supporting Experiments | Key Finding |
| :-- | :--- | :--- | :--- |
| **C1** | Per-relation world-assumption routing on heterogeneous KGs prevents false contradictions on sparse relations without sacrificing overall accuracy compared to fixed CWA. | E2, E3 | Verified on RMIT ($54.00\%$ E2E Acc, $0.5069$ Macro-F1). Dynamic $C(R)$ routing achieves $53.33\%$ overall accuracy and $0.5011$ Macro-F1. |
| **C2** | Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment. | E4, E5 | Continuous score tie-breaking achieves $\text{AURC} = 0.0421$ and $53.67\%$ accuracy at $62.7\%$ coverage under single-pass evaluation. |
| **C3** | Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can. | E6, E7 | On FactKG under forced-binary normalization, $20/318$ ($6.29\%$) of penalized abstentions were verified as genuine refusals where DBpedia context triples were missing. |
| **C4** | Post-hoc claim-level verification is deployable on closed institutional catalogs with a calibrated FCR-Recall tradeoff governed by an abstention threshold ($\theta$) sweep. | E8, E9 | On Catalog2, all Azure models (`azure-4.1-mini`, `azure-5-mini`, `azure-4.1`) achieve **0.00% False Contradiction Rate (0/67)** with **100.00% Contradiction Recall**. |

---

## 2. Headline Multi-Model Evaluation across Azure OpenAI Deployments

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

## 3. Statistical Monotonicity & Holm-Bonferroni Correction

Monotonic adjusted p-values ($p^{adj}_{(k)} = \max_{j \le k} \min(1, p_{(j)} \cdot (m - j + 1))$):

| Dataset | Raw p-value | Rank ($k$) | Multiplier ($m-k+1$) | Monotonic Adjusted p-value | Significance ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | $0.012$ | 1 | 4 | **$0.048$** | **Significant** |
| **FactKG** | $0.038$ | 2 | 3 | **$0.114$** | Not Significant |
| **CoDEx-S** | $0.045$ | 3 | 2 | **$0.114$** | Not Significant |
| **MetaQA** | $0.082$ | 4 | 1 | **$0.114$** | Not Significant |
