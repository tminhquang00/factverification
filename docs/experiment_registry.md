# Experiment Registry

> [!IMPORTANT]
> No existing headline result artifact is currently authoritative. The machine-readable source of status is [`experiments/registry.json`](../experiments/registry.json).

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
| Stage-3 `mapped` name shadowing | `fixed_and_verified` | Repaired; regression test added; suite 23 → 25 |
| Harness substitutes default label on exception | `confirmed_defect_requires_fix` | **Still present.** Crashes are scored as predictions |
| **Rerun 2026-07-25 post-fix multi-model** | `candidate` | **Current primary results.** Cite via `rerun_20260725_paper.md`; not validated |
| LLM pipeline run-to-run variance | `candidate` | 5.75% mean prediction flip rate; single-run gaps <2 pts not resolvable |
| Legacy master sweep | `disabled` | Do not run |

## Next Authoritative Entry Points

The next result-producing runner must be created only after it can emit:

1. A run manifest with code, data, graph, model, prompt, and seed hashes.
2. One row per example and experimental condition.
3. Aggregate metrics derived exclusively from those rows.
4. Explicit calibration and test split identities.
5. A registry entry created with status `candidate`, promoted to `validated` only after consistency checks pass.
