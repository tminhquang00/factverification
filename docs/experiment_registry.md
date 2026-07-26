# Experiment Registry

> [!IMPORTANT]
> No existing headline result artifact is currently authoritative. The machine-readable source of status is [`experiments/registry.json`](../experiments/registry.json). For a narrative synthesis of every entry added or changed on 2026-07-26, see [`journal_20260726.md`](journal_20260726.md).

## Artifact Policy

* Only entries marked `validated` may support a research claim.
* Every future aggregate must be reconstructable from row-level predictions.
* Invalidated outputs remain in the repository only for forensic comparison.
* Rerunning a repaired implementation does not rehabilitate an old output file; new artifacts require new IDs and manifests.

## Current Status

| Experiment | Status | Decision |
| --- | --- | --- |
| Store and graph-path isolation | `validated` | May be cited as an engineering regression only |
| Concurrent transient-context isolation | `validated` | May be cited as an engineering regression only |
| E0.1 graph destruction | `invalidated_requires_rewrite` | Do not cite |
| E2 routing ablation | `implementation_repaired_requires_rerun` | Do not cite old output |
| E3 denominator ablation | `invalidated_simulated` | Delete from future experiment runner |
| E4 threshold sweep | `invalidated_simulated` | Replace with row-level measured sweep |
| E5 meta-confidence | `invalidated_label_leakage` | Replace synthetic features before reuse |
| RMIT claim benchmark | `component_only_not_advising_completeness` | Use only for parser/verifier smoke tests |
| Public tri-state datasets | `invalidated_heldout_edges_present` | Rebuild graph views before evaluation |
| RMIT prerequisite completeness v0 | `synthetic_candidate_not_advisor_audited` | Use for component development, not paper claims |
| E0 prerequisite graph destruction v0 | `candidate_component_control` | Destruction sensitivity is usable for development; baseline performance is not an independent efficacy result |
| RMIT expected-set audit v0 | `awaiting_single_expert_review` | Review test/calibration courses before revising the dataset |
| Rerun 2026-07-25 pre-fix multi-model | `candidate_blocked_by_implementation_defect` | Superseded; retained as the defect case study only |
| Stage-3 `mapped` name shadowing | `fixed_and_verified` | Repaired; regression test added |
| Harness substitutes default label on exception | `fixed_and_verified` | **Repaired 2026-07-26.** Crashes leave the row unscored; `n_scored` reported |
| Stage-3 object namespace substitution | `fixed_and_verified` | Object now compared in the graph's label namespace. CoDEx `Supported` recall 0.039 → 0.974 |
| Entity-link rejection threshold | `candidate` | Configurable; 0.95 dev-selected for CoDEx. Calibrated on one graph only |
| Stage-3 relation normalization | `fixed_and_verified` | Fallback now fires on non-canonical LLM relation phrasings |
| Unresolved claims vote in aggregation | `implemented_measured_disabled_by_default` | Benefit inside noise floor (+0.8 CoDEx), cost reproducible (−2.67 RMIT). Behind `--withhold_unresolved_claims` |
| Rerun 2026-07-25 post-fix multi-model | `candidate` | Superseded by the 2026-07-26 study |
| Rerun 2026-07-26 final public benchmarks (D1–D5 only) | `candidate` | **Superseded** by the cleangraph run below — its CoDEx/MetaQA graphs carried fabricated course scaffolding. Retained via `rerun_20260726_paper.md` as the D1–D5 defect record; not citable for headline numbers |
| CoDEx LLM-pipeline graph destruction | `candidate` | Prediction change 1.8–2.8% → 28.9%. RQ1 affirmative for the LLM pipeline on CoDEx |
| FactKG prefix-sampling artifact | `candidate` | Prefix slice covers 2 of 13 reasoning types; arms differ 23–27 pts on identical code |
| LLM pipeline run-to-run variance | `candidate` | 5.75% mean prediction flip rate; single-run gaps <2 pts not resolvable |
| Legacy master sweep | `disabled` | Do not run |
| E9 baseline suite | `invalidated_fabricated` | Reported hard-coded constants as measured baselines. Script and standalone artifact **deleted 2026-07-26**; recoverable from git history |
| Public-graph course-scaffolding contamination | `defect_open` | Both converters, the transient-context builder, and 3 `KGStore` accessors fabricated course structure on every non-course entity. Fields removed; the routing-signal consequence is tracked as an open defect, not silently repaired |
| Converter seed did not control the split | `fixed_and_verified` | `list(set(...))` before `random.shuffle()` under hash randomization meant the seed controlled nothing. CoDEx converter output is now byte-reproducible |
| RMIT generator unseeded, accepted empty paraphrases | `fixed_and_verified` | No seed anywhere; empty LLM completions were written verbatim on exception-only fallback. Shipped set regenerated with `azure-4.1-mini`: 300/300, 0 empty |
| **Rerun 2026-07-26 cleangraph public benchmarks** | `candidate` | **Current primary results** (`rerun_20260726_cleangraph`, de-scaffolded graphs). Cite via `rerun_20260726_cleangraph_paper.md`; not validated. De-scaffolding moved paired accuracy by at most 1.2 pts (negative result); CoDEx routing-informative relations rose 18/25 → 23/25 |
| RMIT `text` field is a question, not a response | `defect_open` | Measured at full scale 2026-07-26: `raw_claim` 89.67% vs. `text` 45.33% (paired, n=300), but the drop is dominated by correct abstention on the 50.67% of rows holding a question, not an assertion. "Verify `text` instead" is not implementable as written |
| **NUSMods institutional benchmark** | `candidate` | Non-circular tri-state benchmark, 11,647 NUS modules. Pipeline 99.80%/99.40% (azure/gemma) vs. 33.80% floor; graph-destruction gate PASS (0.2907); engine gap 18.80 pts on flat context vs. 0.40 pts (n.s.) inside the pipeline. Deliberately blind to C1; headline sits at its own stage-4 ceiling |

## Next Authoritative Entry Points

The next result-producing runner must be created only after it can emit:

1. A run manifest with code, data, graph, model, prompt, and seed hashes.
2. One row per example and experimental condition.
3. Aggregate metrics derived exclusively from those rows.
4. Explicit calibration and test split identities.
5. A registry entry created with status `candidate`, promoted to `validated` only after consistency checks pass.
