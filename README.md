# Incompleteness-Aware Knowledge-Graph Verification

This repository implements post-hoc verification of long-form answers against structured knowledge
graphs. It distinguishes `Supported`, `Contradicted`, `Not-in-KG`, and `Out-of-scope` using explicit
per-relation completeness declarations.

> **Current result:** the 2026-08-03 end-to-end automated study is complete across hosted
> `azure-4.1-mini` and local `google/gemma-4-e4b` through LM Studio. The direction has a defensible
> methodology/failure-analysis contribution, but the result is not independently validated or
> journal-ready. Start with [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).

## Main finding

On the 200-question NUSMods study, binary absence handling increasingly calls missing graph facts
contradictions. For Azure self-detection under random deletion, false-contradiction rate rises from
5.1% at full retention to 63.6% at 80%, 88.8% at 50%, and 96.3% at 20%. Explicit completeness
declarations keep false-contradiction rate at zero under the study's mechanical labels while safely
returning more `Not-in-KG` decisions.

This is automated candidate evidence. Gold and routing use independently implemented logic but share
researcher-authored graph/declaration semantics; no human review was performed.

## What retention means

`100/95/90/80/50/20%` are nominal **relation-fact retention** targets. All module nodes remain.
For example, 80% means approximately 80% of credit, school, prerequisite, preclusion, and offered-
semester facts remain and approximately 20% are deleted. Clustered department deletion can depart
from the nominal value; manifests record the realized rate. The percentages are unrelated to model
accuracy or two-pass decomposition agreement.

## Pipeline

1. Generate long-form answers under closed-book, full graph-context, or degraded graph-context.
2. Decompose each answer twice and retain normalized claims that agree across passes.
3. Link subjects and objects with exact IDs, labels, dense similarity, and NIL rejection.
4. Normalize schema-gated relation phrases and recover embedded institutional values.
5. Verify triples with relation-specific symbolic logic.
6. Route absence with declarations, occupancy ablations, or binary collapse.
7. Save row-level outputs, hashes, usage, errors, and clustered-bootstrap analyses.

Confidence is heuristic. The calibration experiment is diagnostic and provides no conformal or
deployment-safety guarantee.

## Repository map

- `verification_pipeline.py`: decomposition, linking, relation mapping, verification, aggregation.
- `kg_store.py`: isolated graph stores, declarations, and cached occupancy.
- `data/completeness_declarations/`: explicit dataset relation status.
- `scripts/build_degraded_graphs.py`: random/clustered deletion with logs and manifests.
- `scripts/run_incompleteness_pilot.py`: answer generation, decomposition, mapping, and pilot output.
- `scripts/rescore_incompleteness_sweep.py`: deterministic multi-seed/multi-retention rescore.
- `scripts/analyze_stage_attribution.py`: oracle and end-to-end stage ceilings.
- `scripts/run_flat_context_incompleteness.py`: oracle-context LLM baseline.
- `scripts/run_minicheck_incompleteness.py`: pinned MiniCheck baseline.
- `scripts/run_benchmark_sweep.py`: isolated public-transfer cells and process manifest.
- `experiments/registry.json`: current machine-readable evidence ledger.

## Verify the checkout

```powershell
& .venv\Scripts\python.exe -m pip install -r requirements-experiments.txt
& .venv\Scripts\python.exe -m unittest discover -s tests
```

Expected result: **101 tests pass**.

Deterministic graph-destruction gates also pass: 34.76% mean shuffled prediction change on NUSMods
and 29.53% on CoDEx, both above the required 20% threshold.

## Documentation

- [Current status](docs/CURRENT_STATUS.md)
- [Comprehensive final study](docs/benchmarks/comprehensive_final_study_20260803.md)
- [Methodology of record](docs/architecture/methodology.md)
- [Benchmark construction](docs/benchmark_construction.md)
- [Experiment runbook](docs/experiment_runbook.md)

The docs tree intentionally contains no duplicate implementation-status pages, dated pilot reports,
or draft papers. Removed material remains available through Git history.
