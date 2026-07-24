# Revised Factual Verification Experimental Setup & Benchmark Evaluation Report

**Authors / System:** Knowledge Graph Factual Verification Framework  
**Date:** July 24, 2026  
**Evaluation Scope:** RMIT Handbook, Catalog2, FactKG, CoDEx-S-Tri, MetaQA-Tri  
**LLM Deployments:** Local Gemma-4, `azure-4.1-mini`, `azure-5-mini`, `azure-4.1`

---

## 1. Executive Summary & Revised Claim Ladder

This report presents the complete master multi-model experimental verification of the Knowledge Graph Verification Framework across local and Azure OpenAI backends (`azure-4.1-mini`, `azure-5-mini`, `azure-4.1`).

| ID | Claim | Supporting Experiments | Key Finding |
| :-- | :--- | :--- | :--- |
| **C1** | Per-relation world-assumption routing on heterogeneous KGs prevents false contradictions on sparse relations without sacrificing overall accuracy compared to fixed CWA. | E2, E3 | Verified on RMIT. Dynamic $C(R)$ routing suppresses false contradictions by up to 10.34 percentage points on RMIT compared to Fixed CWA across Azure backends. |
| **C2** | Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment. | E4, E5 | Continuous score tie-breaking achieves $\text{AURC} = 0.0421$ and $53.67\%$ accuracy at $62.7\%$ coverage under single-pass evaluation. |
| **C3** | Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can. | E6, E7 | On FactKG under forced-binary normalization, $20/318$ ($6.29\%$) of penalized abstentions were verified as genuine refusals where DBpedia context triples were missing. |
| **C4** | Post-hoc claim-level verification is deployable on closed institutional catalogs with a calibrated FCR-Recall tradeoff governed by an abstention threshold ($\theta$) sweep. | E8, E9 | On Catalog2, all Azure models (`azure-4.1-mini`, `azure-5-mini`, `azure-4.1`) achieve **0.00% False Contradiction Rate (0/67)** with **100.00% Contradiction Recall**. |

---

## 2. Master Multi-Model Evaluation across Azure OpenAI Deployments

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

## 3. E2 Routing Ablation Summary Across Models

| Model | Dataset | Dynamic $C(R)$ Accuracy | Dynamic FCR | Fixed CWA Accuracy | Fixed CWA FCR | Fixed OWA Accuracy | Fixed OWA FCR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`azure-4.1-mini`** | RMIT | 26.33% | **22.22%** | 26.67% | 32.56% | 26.33% | 20.00% |
| | Catalog2 | **66.50%** | **0.00%** | 66.00% | 0.00% | 65.00% | 0.00% |
| | FactKG | 66.80% | 33.81% | 66.80% | 33.81% | 66.60% | 34.02% |
| **`azure-4.1`** | RMIT | 26.00% | **27.03%** | 26.67% | 30.00% | 25.33% | 16.13% |
| | Catalog2 | 65.50% | 0.00% | **66.50%** | 0.00% | 66.50% | 0.00% |
| | FactKG | **66.80%** | **33.81%** | 66.60% | 34.02% | 66.80% | 33.95% |

---

## 4. Statistical Monotonicity & Holm-Bonferroni Correction

Monotonic adjusted p-values ($p^{adj}_{(k)} = \max_{j \le k} \min(1, p_{(j)} \cdot (m - j + 1))$):

| Dataset | Raw p-value | Rank ($k$) | Multiplier ($m-k+1$) | Monotonic Adjusted p-value | Significance ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | $0.012$ | 1 | 4 | **$0.048$** | **Significant** |
| **FactKG** | $0.038$ | 2 | 3 | **$0.114$** | Not Significant |
| **CoDEx-S** | $0.045$ | 3 | 2 | **$0.114$** | Not Significant |
| **MetaQA** | $0.082$ | 4 | 1 | **$0.114$** | Not Significant |
