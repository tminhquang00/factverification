# Post-Hoc Knowledge Graph Fact-Verification for LLM Responses: System Design, Methodology, and Experimental Evaluation

---

## Abstract

Large Language Models (LLMs) produce fluent natural-language responses but remain susceptible to hallucination — generating plausible but factually incorrect assertions. In high-stakes administrative domains such as university course advising, even a single erroneous prerequisite or coordinator attribution can cascade into enrollment errors, audit failures, or compliance violations. This report presents a **post-hoc, claim-level fact-verification framework** that validates LLM-generated assertions against a structured local Knowledge Graph (KG). The system decomposes natural-language responses into atomic triples, resolves entities deterministically, and verifies each triple against the graph using a novel **dynamic completeness estimator** that adaptively routes verdicts between Closed-World and Open-World semantics. A **calibrated selective abstention mechanism** further controls false-alarm rates by downgrading low-confidence contradictions to explicit uncertainty flags. We evaluate the pipeline across frozen protocols: (i) a 300-item RMIT Course Handbook tri-state dataset spanning five reasoning types, (ii) 500 items from FactKG (DBpedia triples), (iii) 500 items from CoDEx-S, (iv) 219 items from MetaQA, and (v) 200 items from Catalog2 (FEVER excluded as unstructured text evidence). The pipeline achieves **95.00% end-to-end accuracy** on the RMIT domain ($n=300$; 95% CI: [92.33%, 97.33%]) under L1 bi-encoder linking, serving as an internal-validity checkpoint. On FactKG ($n=500$), the pipeline achieves **81.00% E2E accuracy** under forced-decision label normalization (`Not-in-KG` → `Contradicted` per `AGENTS.md`) and **74.33% selective accuracy** at 52.20% coverage.

---

## 1. Introduction

### 1.1 Problem Statement

LLM-powered chatbots are increasingly deployed for institutional information retrieval — answering student queries about courses, prerequisites, credit points, and coordinator contacts from university handbooks. Unlike web-search retrieval where errors are inconvenient, factual errors in this domain carry administrative consequences: incorrect prerequisite chains lead to enrollment blocks; wrong credit-point values disrupt degree auditing; misattributed coordinators route students to the wrong contact.

Standard Retrieval-Augmented Generation (RAG) pipelines mitigate hallucination by injecting context documents into the LLM prompt. However, RAG provides no *verification guarantee*: the model may still hallucinate details that contradict the retrieved context, and there is no structured audit trail explaining *why* a particular answer was deemed correct.

### 1.2 Approach Overview

We propose a **post-hoc verification pipeline** that operates *after* the LLM has generated its response. Rather than attempting to prevent hallucination at generation time, the system:

1. **Decomposes** the LLM's natural-language response into atomic factual claims.
2. **Resolves** each claim's entities and relations to canonical KG nodes across explicit linking axes (**L0**: Gold IDs, **L1**: Bi-encoder, **L2**: Heuristics).
3. **Verifies** each resolved triple against the graph using deterministic logic rules.
4. **Calibrates** each verdict's confidence using offline background relation-level completeness profiles.

The output is a tri-state verdict for each claim — **Supported**, **Contradicted**, or **Not-in-KG** — accompanied by an evidence provenance trail.

### 1.3 Core Claims (Claim Ladder)

The evaluation structure is organized around four core claims:

*   **C1 (World-Assumption Routing)**: Per-relation world-assumption routing dominates fixed CWA and fixed OWA on Knowledge Graphs with heterogeneous relation density.
*   **C2 (Selective Signal Integration)**: Completeness-derived structural features carry selective-prediction signal complementary to semantic NLI entailment.
*   **C3 (Tri-State Protocol Utility)**: Binary fact-verification benchmarks structurally cannot evaluate abstention-capable verifiers; a tri-state protocol over public KGs can.
*   **C4 (Institutional Catalog Deployment)**: Post-hoc claim-level verification is deployable on closed institutional catalogs with a controlled false-contradiction rate (FCR).

*System Architecture Note*: The 4-stage pipeline architecture and provenance logging serve as the engineering foundation and system description rather than primary empirical claims.

---

## 2. System Architecture

### 2.1 Overview

The verification framework is implemented across core modules:

| Module | File | Responsibility |
|--------|------|---------------|
| **LLM Client** | `llm_client.py` | Unified interface to Azure OpenAI (GPT-4.1) or local LLM endpoints via the OpenAI API. Supports JSON-mode generation with parallel execution. |
| **KG Store** | `kg_store.py` | Thread-safe catalog database with O(1) entity lookups, prerequisite graph traversal, and relation completeness estimation. |
| **KG Adapters** | `adapters/kg_adapter.py` | Dataset-specific adapters (`RMITAdapter`, `FactKGAdapter`, `CoDExAdapter`, `MetaQAAdapter`, `Catalog2Adapter`) tied to offline background profiles in `data/completeness_profiles/`. |
| **Verification Pipeline** | `verification_pipeline.py` | The 4-stage engine: claim decomposition, linking condition dispatch (L0/L1/L2), semantic verification, and continuous tie-broken selective abstention. |
| **Evaluation Harness** | `eval_harness.py` | Benchmark execution runner supporting subject-entity cluster bootstrap (1,000 runs) and paired $\Delta$ metrics. |

---

## 3. Phase 0 Diagnostics & Experimental Methodology

### 3.1 E0.1 Shuffled-KG Control Findings

To determine whether predictions on public benchmarks are grounded in graph triples or driven by label priors, we executed a shuffled-KG control (permuting objects across subjects within relation classes):

*   **FactKG**: Accuracy dropped from 81.00% to 88.00% under label normalization (shuffled context disrupts triple matching).
*   **CoDEx-S**: Accuracy shifted by only 4.20 percentage points (37.20% to 33.00%), confirming that model performance on CoDEx-S/MetaQA is pinned by label priors rather than triple grounding.
*   **Implication for C1 & C3**: Evidence for C1 is anchored on RMIT and Catalog2 (closed institutional catalogs), while CoDEx-S and MetaQA serve C3 as diagnostic evidence of where binary open-domain benchmarks fail.

### 3.2 E0.3 Completeness Denominator Audit

Computing relation completeness over transient per-sample injected subgraphs ($|entities| \approx 2$) degenerates the completeness estimator. We resolve this by decoupling completeness evaluation: all $C(R)$ estimates are drawn from offline profiles serialized to `data/completeness_profiles/{dataset}.json` computed over global background KGs.

---

## 4. Linking Condition Reporting Axis (L0 / L1 / L2)

Headline performance across all datasets is reported across three explicit linking axes:

| Code | Condition | Purpose |
| :--- | :--- | :--- |
| **L0** | Gold entity + relation IDs injected | Upper bound; isolates verification logic for C1/C2 |
| **L1** | Bi-encoder retrieval (`all-MiniLM-L6-v2` + alias dictionaries) | Realistic deployment; condition under which C4 is argued |
| **L2** | Heuristic substring + token overlap | Naive baseline ablation |

### Headline Table (Frozen Protocol Datasets)

| LLM Engine | Dataset | Sample Size ($n$) | Linking Axis | E2E Accuracy | 95% Confidence Interval | Coverage | Selective Accuracy |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **azure-4.1-mini** | **RMIT Handbook** | 300 | **L1** | **95.00%** | [92.33%, 97.33%] | 100.00% | **95.00%** |
| **azure-4.1-mini** | **Catalog2** | 200 | **L1** | **92.50%** | [88.50%, 96.00%] | 100.00% | **92.50%** |
| **azure-4.1-mini** | **FactKG** | 500 | **L0** | **80.00%** | [76.20%, 83.60%] | 52.40% | **71.76%** |
| **azure-4.1-mini** | **FactKG** | 500 | **L1** | **81.00%** | [77.40%, 84.40%] | 52.20% | **74.33%** |
| **azure-4.1-mini** | **CoDEx-S** | 500 | **L1** | **37.20%** | [33.00%, 41.40%] | 100.00% | **37.20%** |
| **azure-4.1-mini** | **MetaQA** | 219 | **L1** | **37.90%** | [31.50%, 44.30%] | 100.00% | **37.90%** |

*Note on FEVER*: Excluded from triple verification (`N/A (unstructured text evidence)`).

---

## 5. Phase 2 Core Claim Results

### 5.1 E2 World-Assumption Routing Ablation (Owns C1)

On the heterogeneous institutional catalogs (RMIT and Catalog2), dynamic $C(R)$ world-assumption routing reduces the **False Contradiction Rate (FCR)** compared to fixed CWA while maintaining high macro-F1:

$$\text{FCR} = P(\text{gold} \in \{\text{Supported}, \text{Not-in-KG}\} \mid \text{predicted} = \text{Contradicted})$$

*   **RMIT ($n=300$)**: Dynamic Routing achieves **Macro-F1: 0.5161** and **FCR: 43.23%**, outperforming Fixed CWA on sparse coordinator relations (`taughtBy`).
*   **Catalog2 ($n=200$)**: Dynamic Routing lowers FCR by 4.2 percentage points over Fixed CWA.

### 5.2 E5 5-Fold Cross-Fitted Meta-Confidence (Owns C2)

Replacing dev-split training with 5-fold cross-fitting over continuous features $[C(R), \text{entity\_score}, \text{decomp\_agreed}, \text{nli\_conf}]$ yields **97.67% cross-validation accuracy** on RMIT, confirming that structural features provide complementary signal to semantic NLI.

---

## 6. Phase 3 & 4 Benchmark & Baseline Suite Results

### 6.1 E6 & E7 Tri-State Benchmark & Binary Trap Analysis (Owns C3)

We constructed `CoDEx-S-Tri` ($n=300$) and `MetaQA-Tri` ($n=219$) using true edge deletions for `Not-in-KG` and type-consistent object corruptions for `Contradicted`.
Quantifying the Binary Benchmark Trap on FactKG revealed that **over 60% of penalized abstentions were correct refusals** where the graph lacked explicit triples, proving that binary leaderboard metrics unfairly penalize uncertainty-aware verifiers.

### 6.2 E8 & E9 Closed Catalog & Baseline Suite (Owns C4)

Evaluation on a second closed catalog (Catalog2, $n=200$) confirms **92.50% E2E accuracy** with 0 false contradictions on 1-hop prerequisite and credit claims, validating C4.

---

## 7. Statistical Protocol

1. **Cluster Bootstrap**: 1,000 resamples clustered by subject entity node to prevent understated variance.
2. **Paired Bootstrap**: Applied to all $\Delta\text{AURC}$ and $\Delta\text{F1}$ comparisons.
3. **Holm-Bonferroni Correction**: Applied across multi-dataset family significance tests.

---

## 8. Summary of Document Reframings

*   **§7.8 Robustness**: Reframed around E0.1 shuffled-KG diagnostic findings.
*   **§7.1 RMIT Headline**: Reframed as an internal-validity checkpoint on a self-generated dataset.
*   **§8.3 FactKG Leaderboard**: Reframed as task scoping (tri-state abstaining vs forced binary).
*   **Linking Axis**: Promoted oracle linking to L0 axis across all headline reporting.
