# Research Implementation Status

**Updated:** 2026-07-25  
**Current scope decision:** RMIT first; synthetic Catalog2 is an engineering control only.  
**Expert-review design:** One handbook reviewer; no inter-annotator agreement claim.

## Completed

### Evidence quarantine

* Created the machine-readable [`experiments/registry.json`](../experiments/registry.json).
* Marked historical benchmark and calibration reports as invalidated.
* Disabled legacy runners that generated simulated, label-conditioned, or hand-written statistics.

### Evaluation substrate

* Removed the path-insensitive global `KGStore` singleton.
* Isolated transient per-example graphs and restored background graph/index state.
* Removed claim-local decomposition and entity scores from the shared core execution path.
* Implemented explicit `dynamic`, `fixed_cwa`, and `fixed_owa` routing treatments.
* Renamed the graph-density statistic to relation occupancy and retained the old completeness method only as a compatibility alias.
* Disabled legacy heuristic abstention by default and labeled its confidence uncalibrated.

### Completeness implementation

* Added deterministic `QuerySpec`, expected-answer computation, response-member extraction, set precision/recall, exact-set match, and explicit missing/unexpected members.
* Integrated claim correctness and answer completeness as separate pipeline outputs.
* Added a dual-risk controller with independent wrong-answer and omission budgets. Uncalibrated risk estimates always defer.

### Candidate data and controls

* Generated 181 RMIT prerequisite-section membership responses across 50 courses.
* Grouped development/calibration/test splits by course, not response row.
* Added complete, omission, distractor, and corruption conditions.
* Generated a paired graph-destruction control over 33 test responses with baseline, empty graph, and five within-relation zero-fixed-point derangements.
* Saved 231 row-level control predictions, graph/artifact hashes, and subject-clustered paired intervals.

### Expert audit workflow

* Generated a one-row-per-course audit CSV linked to all 50 cached handbook HTML pages and live URLs.
* Added the review protocol and mechanical validator.
* Current review status: `awaiting_review`; 20 calibration/test courses remain required.

## Current Candidate Result

The deterministic component is graph-sensitive on the synthetic test split:

| Condition | Accuracy | Observed drop | Subject-clustered 95% CI for drop |
| --- | ---: | ---: | ---: |
| Baseline | 100.0% | 0.0% | [0.0%, 0.0%] |
| Empty graph | 48.5% | 51.5% | [42.9%, 56.8%] |
| Shuffled graph, five seeds | 57.6% | 42.4% | approximately [34.5%, 48.5%] |

This is a component grounding check, not an efficacy claim. Baseline gold labels and predictions share the same expected-set query, and the source sets have not yet been independently audited.

## Next Work

1. Complete the single-expert audit for test and calibration courses using [`advisor_audit_protocol.md`](advisor_audit_protocol.md).
2. Apply corrections to a new graph and benchmark version; do not edit v0 artifacts in place.
3. Parse prerequisite Boolean structure (`AND`, `OR`, alternatives, non-course conditions) from source pages.
4. Add title/paraphrase answer-member linking and clean L0/L1/L2 extraction conditions.
5. Add an independently labeled response set and LLM-as-judge baseline.
6. Collect calibration-only score/label pairs before enabling any risk-controlled acceptance.

## Verification

Run:

```powershell
& .venv\Scripts\python.exe -m unittest discover -s tests -v
```

Current result: 23 tests passing.
