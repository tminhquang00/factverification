# Current Status

**Updated:** 2026-08-03
**Branch:** `codex/fix-data-generation-pipeline`
**Study status:** automated end-to-end rerun complete
**Research status:** `candidate_automated` — not independently validated
**Models:** hosted `azure-4.1-mini`; local `google/gemma-4-e4b` through LM Studio

## At a glance

| Area | Status | Meaning |
| --- | --- | --- |
| Data and degradation pipeline | Complete | Fixed NUSMods/RMIT inputs, manifests, three seeds, random and clustered deletion |
| Long-form model matrix | Complete | Azure/Gemma self and cross-detector arms; saved answers reused across detectors |
| Baselines | Complete | Declared, binary, occupancy, oracle-context Azure/Gemma, and pinned MiniCheck |
| Transfer | Complete | NUSMods, RMIT, FactKG, and CoDEx public cells for both models |
| Engineering verification | Passing | 101 tests; NUSMods/CoDEx destruction gates pass |
| Human validation | Intentionally skipped | Questions, declarations, and gold remain researcher/mechanically defined |
| Publication readiness | Thesis/workshop candidate | Not journal-ready; see the comprehensive assessment |

## Headline result

Binary absence handling becomes unsafe as graph facts disappear. Pooled random-deletion
false-contradiction rate (FCR), across three seeds and all answer conditions:

| Generator -> detector | 100% | 80% | 50% | 20% |
| --- | ---: | ---: | ---: | ---: |
| Azure -> Azure | 5.1% | 63.6% | 88.8% | 96.3% |
| Azure -> Gemma | 17.5% | 71.8% | 92.6% | 97.7% |
| Gemma -> Azure | 40.9% | 86.9% | 95.8% | 98.6% |
| Gemma -> Gemma | 62.5% | 90.1% | 96.4% | 99.1% |

The declared tri-state route records zero false contradictions in these conditions under mechanical
gold. That is a semantic consistency result, not independent efficacy: routing and gold are
separately implemented but share researcher-authored graph/declaration semantics.

Decision coverage falls as missingness grows because the declared system returns `Not-in-KG`
instead of making false binary decisions. For Azure self-detection under random deletion, declared
decision coverage changes from 99.3% at 100% retention to 31.7% at 20%.

## What 100%, 80%, 50%, and 20% mean

They are **nominal relation-fact retention targets**, not percentages of questions, answers, module
nodes, confidence, or decomposition agreement. All 11,647 NUSMods modules stay in every graph.

| Retention | Approximate facts removed from each selected relation |
| ---: | ---: |
| 100% | 0% |
| 80% | 20% |
| 50% | 50% |
| 20% | 80% |

Selected relations are credits, faculty/school, prerequisites, preclusions, and offered semesters.
Staffing remains naturally incomplete and is not artificially degraded.

Random mode deletes individual facts and is exact to rounding. Clustered mode deletes department
groups, so realized retention varies with group size. Every manifest records requested and realized
values per relation.

“Each answer was decomposed with two-pass self-consistency” is a separate statement: the detector
runs twice at temperatures `0.1` and `0.2` and retains normalized atoms appearing in both passes.

## End-to-end stage result

All 300 NUSMods expected triples reach 100% under verification-only and linking-plus-verification
oracle arms. Stage 4 also reaches 100% on the final extracted atoms in every model pairing. The main
end-to-end loss occurs before symbolic verification.

Full-context expected-triple results:

| Generator -> detector | Extraction coverage | F1 | Exact expected set |
| --- | ---: | ---: | ---: |
| Azure -> Azure | 87.5% | 98.6% | 96.6% |
| Azure -> Gemma | 80.0% | 91.1% | 79.0% |
| Gemma -> Azure | 76.5% | 87.4% | 77.8% |
| Gemma -> Gemma | 70.0% | 79.7% | 65.3% |

The final mapping repair recovers values embedded in Gemma relation phrases and maps unrecoverable
values to `object_unresolved -> Not-in-KG`, avoiding false mismatches.

## Baselines and controls

- Azure oracle-context tri-state accuracy is 92.0% at full retention and 64.3% at random 20%; its
  binary collapse is 24.7% at random 20%. This uses oracle-selected relation context, not retrieval.
- Gemma oracle-context tri-state accuracy is 87.3% at full retention and 36.7% at random 20%; its
  binary collapse is 21.7% at random 20%. All 2,700 final rows are scored with no terminal errors.
- MiniCheck native binary accuracy is 71.3-83.3%, but mapping `Unsupported` to `Contradicted`
  creates 100% FCR because MiniCheck has no `Not-in-KG` class.
- Title-only NIL stress test at threshold 0.95: 57.2% total link accuracy, 48.4% In-KB F1, 69.2%
  NIL F1. Course-code oracle linking remains 100%.
- NUSMods shuffled-graph prediction change: 34.76% (PASS, gate 20%).
- CoDEx shuffled-graph prediction change: 29.53% (PASS).
- RMIT set control: 42.4-point shuffle drop and 51.5-point empty-graph drop.
- Final Azure/Gemma transfer accuracy is 99.8%/99.4% on random NUSMods, 84.8%/79.8% on random
  CoDEx, 60.4%/59.0% on random FactKG, and 97.0%/75.0% on full RMIT; every cell has zero harness
  failures. FactKG prefix scores are excluded from the headline because ordering changes sample mix.
- Regression suite: 101 tests passing.

## Publication judgment

The direction has a credible contribution as a controlled methodology and failure analysis:
explicit completeness metadata, tri-state verification, controlled relation deletion, asymmetric
false-contradiction risk, and stage-wise attribution for long-form LLM answers.

- Master's thesis: ready as an automated experimental study.
- Workshop/short paper: plausible with transparent limitations.
- Full conference: borderline without independent labels, natural incompleteness, realistic
  retrieval, and repeated answer-generation runs.
- Journal: not supported by the current automated-only evidence.

Skipping human review was respected. It caps the strength of the publication claim; it does not
erase the controlled experimental finding.

## Important limitations

- Gold, questions, and declarations are graph/researcher derived.
- The context-generation and flat verifier arms use oracle subject/relation selection.
- One stochastic answer run is saved per generator/condition.
- Cross-detector decomposition is stochastic even when answer text is fixed.
- Occupancy is graph density, not real-world completeness, and behaves non-monotonically.
- Confidence is heuristic; calibration is descriptive, not conformal.
- RMIT is small; FactKG is binary and strongly affected by prefix versus random sampling.
- Data-release rights for source catalog records still require review.

## Sources of truth

- [Comprehensive final report](benchmarks/comprehensive_final_study_20260803.md): results,
  uncertainty, analysis, literature boundary, and publication decision.
- [Methodology of record](architecture/methodology.md): implemented behavior.
- [Benchmark construction](benchmark_construction.md): source data and retention semantics.
- [Experiment runbook](experiment_runbook.md): exact reproduction flow.
- [`experiments/registry.json`](../experiments/registry.json): machine-readable current artifact ledger.

Historical pilots and duplicate status documents are not current evidence and have been removed from
the active docs tree.
