# Knowledge Graph Verification Framework - Documentation

Welcome to the documentation suite for the **Knowledge Graph (KG) Fact-Verification & Calibration Framework**. This directory contains architectural specifications, benchmark analysis, calibration reports, and reproduction walkthroughs.

## Research Roadmap

* **[research_improvement_plan.md](research_improvement_plan.md)**: Evidence-grounded review of the current implementation and a staged plan for rebuilding the study around set-valued answer completeness, calibrated dual-risk deferral, and valid graph-groundedness controls.
* **[experiment_registry.md](experiment_registry.md)**: Authoritative validity status for existing scripts, reports, and result artifacts.
* **[implementation_status.md](implementation_status.md)**: Completed implementation work, candidate artifacts, current limits, and the next executable steps.
* **[advisor_audit_protocol.md](advisor_audit_protocol.md)**: Source-grounded instructions for the selected single-reviewer RMIT expected-set audit.
* **[experiment_runbook.md](experiment_runbook.md)**: Exact PowerShell commands for RMIT, FactKG, and CoDEx experiments, including all saved output paths.

> [!CAUTION]
> Historical benchmark tables below are retained for traceability but are invalidated and must not be cited as research results.

---

## 📁 Directory Structure & Index

### 🏛️ 1. Architecture (`docs/architecture/`)

Split by whether a document describes the **built** system or the **intended** one — see
[architecture/README.md](architecture/README.md) for the index.

* **[methodology.md](architecture/methodology.md)**: **Architecture-of-record.** Pipeline stages with real algorithms and parameters, evaluation protocol, instrumentation rules, and the methodology's own limitations.
* **[system_expert_review.md](architecture/system_expert_review.md)**: Code-level reference — call ordering, fallback chains, thresholds, plus a table of everything previously documented but not implemented.
* **[system_explained_v3.md](architecture/system_explained_v3.md)**: Plain-language walkthrough of the working system.
* **[design.md](architecture/design.md)**: *(design roadmap, largely unbuilt)* Verification-oriented ontology, harness specification, dataset inventory, contribution claims. Carries a build-status map.

> [!WARNING]
> Three things the architecture docs previously stated incorrectly: routing uses **relation occupancy**, not completeness; confidence is **uncalibrated** and **no NLI component exists** anywhere in the codebase; and the offline $C(R)$ profiles in `data/completeness_profiles/` are **dead code** with respect to verification.

---

### 📊 2. Benchmarks & Evaluation (`docs/benchmarks/`)
Empirical research findings across university handbook and public benchmark datasets (`FactKG`, `CoDEx`, `MetaQA`, `FEVER`):

* **[rerun_20260726_paper.md](benchmarks/rerun_20260726_paper.md)**: **Authoritative current study (2026-07-26).** Repairs five implementation defects and re-runs every cell under both sampling protocols. CoDEx moves 41.8% → 81.8% and 37.2% → 75.8% on identical rows; `Supported` recall 0.039 → 0.981; the graph-destruction control moves from 1.8–2.8% to 28.9% prediction change, establishing graph-groundedness for the LLM pipeline for the first time. Also shows FactKG's previous numbers were a prefix-sampling artifact.
* **[comprehensive_report_20260725.md](benchmarks/comprehensive_report_20260725.md)**: Independent review of the 2026-07-25 study that located those defects. Recomputes every headline figure from row-level artifacts, then adds four new diagnostics: the CoDEx `Supported` collapse is an object-namespace bug rather than an entity-linking failure; the LLM verification path is *not* graph-grounded on CoDEx (2–3% prediction change under full content destruction); the FactKG prefix sample covers only 2 of 13 reasoning types; and CoDEx `Not-in-KG` is forfeited by an entity linker with no rejection threshold. Carries corrections to the paper below.
* **[rerun_20260725_paper.md](benchmarks/rerun_20260725_paper.md)**: *(superseded)* The 2026-07-25 measurement-integrity study. Full paper — data provenance, system description, methodology, defect analysis, results, run-to-run reliability, threats to validity, and an explicit statement of what may and may not be claimed. All aggregates are recomputed from row-level predictions.
* **[rerun_20260725_report.md](benchmarks/rerun_20260725_report.md)**: Chronological run log for the same study (pre-fix sweep, repair, post-fix sweep). Carries no results tables.
* **[research_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/research_report.md)**: *(invalidated)* Historical benchmark report including multi-model evaluations, bootstrap CIs, selective accuracy, coverage, and ablation studies.
* **[calibration_report.md](file:///c:/Users/Admin/Desktop/crawler/docs/benchmarks/calibration_report.md)**: *(invalidated)* Historical analysis of tri-state decision calibration, abstention threshold sweeps, and risk-coverage curves.

---

### 🖼️ 3. Visual Assets (`docs/assets/`)
Figures, plots, and visualizations referenced in research reports:

* **`docs/assets/risk_coverage_curves.png`**: Risk vs Coverage curves across confidence estimation methods.
* **`docs/assets/score_distributions.png`**: Confidence score distribution plots for covered vs abstained claims.

---

---

### 🏆 5. Current Study — 2026-07-26 (`rerun_20260726_final`)

Full paper: **[benchmarks/rerun_20260726_paper.md](benchmarks/rerun_20260726_paper.md)**.
Ten cells, recomputed from row-level predictions. Zero unscored rows in every cell.

| LLM Engine | Dataset | Sampling | $n$ | Accuracy | 95% CI (IID rows) | Floor | Macro-F1 | Coverage | Selective Acc. |
|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `azure-4.1-mini` | CoDEx | prefix | 500 | **81.80%** | [78.20%, 85.00%] | 35.80% | 0.819 | 99.80% | 81.80% |
| `azure-4.1-mini` | CoDEx | random | 500 | **83.80%** | [80.40%, 87.00%] | 35.00% | 0.831 | 99.60% | 83.90% |
| `gemma-4-e4b` | CoDEx | prefix | 500 | **75.80%** | [72.00%, 79.40%] | 35.80% | 0.763 | 89.20% | 79.37% |
| `gemma-4-e4b` | CoDEx | random | 500 | **78.60%** | [75.00%, 82.60%] | 35.00% | 0.784 | 91.20% | 82.24% |
| `azure-4.1-mini` | FactKG | prefix | 500 | 83.60% | [80.40%, 86.60%] | 64.60% | 0.821 | 62.20% | 77.17% |
| `azure-4.1-mini` | FactKG | random | 500 | 57.60% | [53.20%, 61.80%] | 52.80% | 0.491 | 69.40% | 58.50% |
| `gemma-4-e4b` | FactKG | prefix | 500 | 82.60% | [79.40%, 85.60%] | 64.60% | 0.797 | 46.60% | 87.55% |
| `gemma-4-e4b` | FactKG | random | 500 | 55.80% | [51.20%, 60.20%] | 52.80% | 0.451 | 62.80% | 59.55% |
| `azure-4.1-mini` | RMIT | full | 300 | 97.33% | [95.33%, 99.00%] | 41.67% | 0.988 | 97.67% | 99.66% |
| `gemma-4-e4b` | RMIT | full | 300 | 90.33% | [86.67%, 93.67%] | 41.67% | 0.913 | 95.67% | 94.42% |

Principal findings:

* **Five implementation defects, not model capability, drove the previous CoDEx result.** The dominant one substituted the resolved entity *key* for a claim's object while graphs store surface labels, so stage 4 reported a value mismatch for every true claim. On identical rows CoDEx moves **41.8% → 81.8%** and **37.2% → 75.8%**, with `Supported` recall **0.039 → 0.981**. Suite 23 → 35 tests.
* **The pipeline is now graph-grounded.** Destroying all factual content while preserving structure changes **28.9%** of predictions, versus 1.8–2.8% before — answering RQ1 affirmatively for the LLM pipeline for the first time.
* **FactKG's previous numbers were a prefix-sampling artifact.** `factkg_test.jsonl` is sorted into contiguous reasoning-type blocks; the first 500 rows cover **2 of 13** types at a 64.60% floor against the full set's 51.35%. Under random sampling accuracy falls to ~58%.
* **FactKG reasoning type determines the gold label almost deterministically** — every `*|substitution` type is ~100% `Contradicted`, every plain `numN` type ~98% `Supported` — so the pipeline's `Contradicted` prior scores 0.94–1.00 on one group and 0.03–0.33 on the other. This is the C3 binary-benchmark trap, measured.
* **Crashes are no longer scored as predictions** in either harness, closing the instrumentation flaw the 2026-07-25 study identified.
* **RMIT's absolute accuracy remains structurally inflated**: `eval_rmit.py:54` verifies a template string interpolated from the same KG fields the verifier then queries. Both RMIT deltas are within the measured noise floor; `gemma-4-e4b` awaits replication.

---

### 📉 6. Historical Multi-Model Table (invalidated — retained for traceability only)

> [!CAUTION]
> The table below predates the evidence quarantine and must not be cited. See
> [experiment_registry.md](experiment_registry.md).

| LLM Engine | Dataset | Evaluated ($n$) | E2E Accuracy | 95% Confidence Interval | Coverage | Selective Accuracy |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **azure-4.1-mini** | **RMIT Handbook** | 300 | **95.00%** | [92.33%, 97.33%] | 100.00% | **95.00%** |
| **azure-4.1-mini** | **FactKG** | 500 | **81.00%** | [77.40%, 84.40%] | 52.20% | **74.33%** |
| **azure-4.1-mini** | **CoDEx-S** | 500 | **37.20%** | [33.00%, 41.40%] | 100.00% | **37.20%** |
| **azure-4.1-mini** | **MetaQA** | 219 | **37.90%** | [31.50%, 44.30%] | 100.00% | **37.90%** |
| **azure-5-mini** | **FactKG** | 500 | **79.60%** | [75.80%, 83.20%] | 51.80% | **75.68%** |
| **azure-5-mini** | **CoDEx-S** | 500 | **37.60%** | [33.40%, 41.80%] | 100.00% | **37.60%** |
| **azure-5-mini** | **MetaQA** | 219 | **40.64%** | [34.20%, 47.10%] | 100.00% | **40.64%** |
| **gemma-4-e4b** | **FactKG** | 500 | **80.00%** | [76.40%, 83.60%] | 36.00% | **87.22%** |
| **gemma-4-e4b** | **CoDEx-S** | 500 | **36.60%** | [32.40%, 40.80%] | 100.00% | **36.60%** |
| **gemma-4-e4b** | **MetaQA** | 219 | **36.53%** | [30.10%, 43.00%] | 100.00% | **36.53%** |

#### Staged Experiments ($n=500$)
- **Exp 1 (Oracle Upper Bound)**: FactKG **80.00% E2E Accuracy**, **71.76% Selective Accuracy** @ 52.40% Coverage.
- **Exp 2 (Neural Entity/Relation Linking)**: CoDEx-S **37.60% E2E Accuracy** with `SentenceTransformer("all-MiniLM-L6-v2")`.
- **Exp 3 (Multi-Hop Decontextualization)**: MetaQA **37.90% E2E Accuracy** @ 100.00% Coverage.
- **Exp 4 (Continuous Calibration Smoothing)**: FactKG **81.40% E2E Accuracy**, **76.06% Selective Accuracy** @ 51.80% Coverage.
