# Knowledge Graph Verification Framework - Documentation

Welcome to the documentation suite for the **Knowledge Graph (KG) Fact-Verification & Calibration Framework**. This directory contains architectural specifications, benchmark analysis, calibration reports, and reproduction walkthroughs.

## Research Roadmap

* **[journal_20260726.md](journal_20260726.md)**: **Start here for 2026-07-26.** Single-document synthesis of every experiment run that day — the five pipeline defects (D1–D5), the five evaluation-substrate defects (S1–S5), and the NUSMods benchmark — with abstract, methodology, dataset, results, and ablation sections, and every number cross-checked against its source paper.
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
Empirical research findings across university handbook and public benchmark datasets (`FactKG`, `CoDEx`, `MetaQA`, `FEVER`, `NUSMods`):

* **[nusmods_study_20260726.md](benchmarks/nusmods_study_20260726.md)**: **Full NUSMods study (2026-07-26, candidate) — the paper.** Both engines × three methods × 500 rows, four validity controls run as gates, an ablation study with exact paired McNemar tests, and a cross-dataset comparison against FactKG / CoDEx / MetaQA / RMIT. Headline is not the 99.80% accuracy but the **engine-gap result**: the two engines differ by 18.80 points given flat triple context ($p = 9.5\times10^{-24}$) and by 0.40 points inside the pipeline ($p = 0.625$, n.s.) — a 4B local model matches a hosted one once the graph does the comparison. The advantage is localized to closed-world set reasoning (`prerequisite-negation`: 100% vs 66%), not lookup. Figures in `output/experiments/nusmods_20260726/analysis/`.
* **[nusmods_benchmark.md](benchmarks/nusmods_benchmark.md)**: Benchmark construction reference for the above — data provenance, graph schema, label convention, and reproduction. **Institutional-catalog benchmark (2026-07-26, candidate).** Tri-state benchmark over 11,647 NUS modules from the NUSMods v2 API, built to remove the circularity that invalidates `eval_rmit.py`: every gold label is world-assumption-independent, so the benchmark cannot score the verifier's own routing policy (and is therefore deliberately blind to C1). Hard negatives are drawn from the catalog's own value distributions. Passes the graph-destruction gate at 0.2907 prediction change; stage-3/4 ceiling 1.0000 at `entity_link_threshold` 0.95 versus 0.7520 at the 0.35 default, where the `Not-in-KG` class collapses. `gemma-4-e4b`: pipeline 99.40%, context 72.00%, closed-book 33.80% against a 33.80% majority floor.
* **[rerun_20260726_cleangraph_paper.md](benchmarks/rerun_20260726_cleangraph_paper.md)**: **Authoritative current study (2026-07-26).** Repairs a construct-validity defect in the *evaluation substrate*: both public-benchmark converters, the transient-context builder, and three `KGStore` accessors fabricated course structure for non-course entities (Leonhard Euler recorded as a 12-credit Science course). Absent values now dispatch through the world assumption instead of being compared against invented placeholders. Also fixes two reproducibility defects — neither converter's seed controlled its split, and the RMIT generator was unseeded and silently wrote empty LLM completions to disk. Headline is a **negative result**: de-scaffolding moves paired accuracy by at most 1.2 pp, inside the noise floor, while the CWA/OWA routing signal on CoDEx improves from 18 to 23 interior relations of 25. First cost and latency measurements.
* **[rerun_20260726_paper.md](benchmarks/rerun_20260726_paper.md)**: *(superseded)* Repairs five implementation defects and re-runs every cell under both sampling protocols. CoDEx moves 41.8% → 81.8% and 37.2% → 75.8% on identical rows; `Supported` recall 0.039 → 0.981; the graph-destruction control moves from 1.8–2.8% to 28.9% prediction change. Also shows FactKG's previous numbers were a prefix-sampling artifact. **Its CoDEx/MetaQA figures were measured against contaminated graphs and its RMIT rows no longer exist.**
* **[comprehensive_report_20260725.md](benchmarks/comprehensive_report_20260725.md)**: Independent review of the 2026-07-25 study that located those defects. Recomputes every headline figure from row-level artifacts, then adds four new diagnostics: the CoDEx `Supported` collapse is an object-namespace bug rather than an entity-linking failure; the LLM verification path is *not* graph-grounded on CoDEx (2–3% prediction change under full content destruction); the FactKG prefix sample covers only 2 of 13 reasoning types; and CoDEx `Not-in-KG` is forfeited by an entity linker with no rejection threshold. Carries corrections to the paper below.
* **[rerun_20260725_paper.md](benchmarks/rerun_20260725_paper.md)**: *(superseded)* The 2026-07-25 measurement-integrity study. Full paper — data provenance, system description, methodology, defect analysis, results, run-to-run reliability, threats to validity, and an explicit statement of what may and may not be claimed. All aggregates are recomputed from row-level predictions.
* **[rerun_20260725_report.md](benchmarks/rerun_20260725_report.md)**: Chronological run log for the same study (pre-fix sweep, repair, post-fix sweep). Carries no results tables.

---

### 🖼️ 3. Visual Assets (`docs/assets/`)
Figures, plots, and visualizations referenced in research reports:

* **`docs/assets/cleangraph_*.png`**: The four figures of the **current** study ([rerun_20260726_cleangraph_paper.md](benchmarks/rerun_20260726_cleangraph_paper.md)) — accuracy overview, sampling delta, coverage vs. selective accuracy, and RMIT by reasoning type. Regenerate with `python scripts/plot_experiment_results.py --dir output/experiments/rerun_20260726_cleangraph`.
* **`docs/assets/rerun_20260726_accuracy_overview.png`**: *(superseded)* Accuracy by dataset / sampling / model with 95% CI, from the previous study ([§3.1](benchmarks/rerun_20260726_paper.md#31-headline)).
* **`docs/assets/rerun_20260726_sampling_delta.png`**: Accuracy(random) − accuracy(prefix) per dataset/model, the sampling-order-effect evidence for [§4](benchmarks/rerun_20260726_paper.md#4-factkg-the-benchmark-was-measuring-a-label-prior).
* **`docs/assets/rerun_20260726_coverage_vs_selective_accuracy.png`**: Coverage vs. selective accuracy across all ten cells.
* **`docs/assets/rerun_20260726_rmit_by_reasoning_type.png`**: RMIT accuracy by reasoning type, azure-4.1-mini vs. gemma-4-e4b ([§3.5](benchmarks/rerun_20260726_paper.md#35-rmit-existence-under-gemma-4-e4b-a-slice-too-noisy-to-attribute)).

---

---

### 🏆 5. Current Study — 2026-07-26 (`rerun_20260726_cleangraph`)

Full paper: **[benchmarks/rerun_20260726_cleangraph_paper.md](benchmarks/rerun_20260726_cleangraph_paper.md)**.
Ten cells, recomputed from row-level predictions. Zero unscored rows in every cell. Supersedes the
`rerun_20260726_final` table previously shown here — that run's CoDEx and MetaQA graphs carried
fabricated course scaffolding on every entity (registry: `public_graph_course_scaffolding_contamination`).
A synthesized read of this table alongside NUSMods and the D1–D5 repair is in
[journal_20260726.md](journal_20260726.md).

| LLM Engine | Dataset | Sampling | $n$ | Accuracy | 95% CI (IID rows) | Floor | Macro-F1 |
|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|
| `azure-4.1-mini` | CoDEx | prefix | 500 | **82.20%** | [78.80%, 85.60%] | 36.40% | 0.824 |
| `azure-4.1-mini` | CoDEx | random | 500 | **83.00%** | [79.40%, 86.20%] | 34.60% | 0.830 |
| `gemma-4-e4b` | CoDEx | prefix | 500 | **75.80%** | [71.80%, 79.60%] | 36.40% | 0.762 |
| `gemma-4-e4b` | CoDEx | random | 500 | **77.40%** | [73.60%, 80.80%] | 34.60% | 0.776 |
| `azure-4.1-mini` | FactKG | prefix | 500 | 83.20% | [80.00%, 86.20%] | 64.60% | 0.816 |
| `azure-4.1-mini` | FactKG | random | 500 | 58.20% | [54.00%, 62.40%] | 52.80% | 0.503 |
| `gemma-4-e4b` | FactKG | prefix | 500 | 81.40% | [78.00%, 85.00%] | 64.60% | 0.784 |
| `gemma-4-e4b` | FactKG | random | 500 | 56.60% | [52.00%, 60.60%] | 52.80% | 0.461 |
| `azure-4.1-mini` | RMIT | full | 300 | 97.33% | [95.30%, 99.00%] | 41.67% | 0.989 |
| `gemma-4-e4b` | RMIT | full | 300 | 89.00% | [85.70%, 92.30%] | 41.67% | 0.906 |

Principal findings:

* **De-scaffolding the evaluation substrate was a negative result, and that is the point.** Both public-benchmark converters, the pipeline's own transient-context builder, and three `KGStore` accessors had fabricated course structure (`credits: 12`, `school: "Science"`, …) onto every non-course entity. Removing it moved paired accuracy (the four FactKG cells, whose rows were untouched) by **at most 1.2 points** — inside the measured 5.75% flip-rate noise floor. It was a construct-validity defect, not an accuracy inflator.
* **What did move: the CWA/OWA routing signal.** CoDEx relations with interior occupancy (informative for routing) rose from **18 of 25 to 23 of 25** once the fabricated always-1.0 occupancy on `hasCreditValue`/`partOfSchool`/`requiresPrerequisite` was removed.
* **Five implementation defects (D1–D5), not model capability, drove the earlier low CoDEx result.** The dominant one substituted the resolved entity *key* for a claim's object while graphs store surface labels. On identical rows CoDEx moved **41.8% → 81.8%** and **37.2% → 75.8%** under that repair alone, with `Supported` recall **0.039 → 0.981**. Suite 23 → 35 → 60 tests.
* **The pipeline is graph-grounded.** Destroying all factual content while preserving structure changes **28.9%** of predictions, versus 1.8–2.8% before the D1–D5 repair.
* **FactKG remains a prefix-sampling artifact.** `factkg_test.jsonl` is sorted into contiguous reasoning-type blocks; the first 500 rows cover **2 of 13** types at a 64.60% floor against the full set's 52.80%. Under random sampling accuracy falls to ~57–58%, and reasoning type determines the gold label almost deterministically (every `*|substitution` type ~100% `Contradicted`, every plain `numN` type ~98% `Supported`) — the C3 binary-benchmark trap, measured.
* **RMIT's absolute accuracy remains structurally inflated**: `eval_rmit.py:54` verifies a template string interpolated from the same KG fields the verifier then queries; measured directly today by running `--verify_field text` on all 300 rows (§7.6 of the journal).

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
