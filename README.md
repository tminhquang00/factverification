# Incompleteness-Aware Knowledge-Graph Verification

This repository implements post-hoc verification of long-form answers against structured knowledge
graphs. It distinguishes `Supported`, `Contradicted`, `Not-in-KG`, and `Out-of-scope`, and it studies
what happens to that distinction as facts disappear from the graph.

> **Current result:** the 2026-08-03 end-to-end automated study is complete across hosted
> `azure-4.1-mini` and local `google/gemma-4-e4b` (LM Studio), rerun under a **declaration-independent
> gold** that removed a circularity in the earlier scoring. The work is ready as a thesis or workshop
> measurement paper; it is not journal-ready. Start with [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).

## A withdrawn claim, and why

An earlier version of this study reported that the proposed `declared` route achieved a **zero
false-contradiction rate everywhere**. That number has been withdrawn.

The old gold function decided whether a missing fact counted as `Contradicted` or `Not-in-KG` by
reading a completeness declaration file — and the proposed system decided the same thing by reading
**the same file**. Different code, identical rule. The system was graded against its own definition
and scored exactly 1.000 accuracy and 1.000 macro-F1 in all 336 cells, with a zero-width confidence
interval. The `binary` baseline was worse: not a system at all, just one line of post-processing on
the proposed system's output, so its "5.1% → 96.3%" curve was arithmetic restating the deletion rate.

Gold is now computed from two graphs only — the undegraded reference snapshot and the damaged graph
the system was allowed to see — and never opens a declaration file
([`scripts/intervention_gold.py`](scripts/intervention_gold.py)). `binary` is a real routing mode. A
new `declared_stale` arm models metadata that was never updated after data loss.

The fix cost the proposed route its perfect score, which is the point: it now measures at 99.0%
accuracy and 0.919 macro-F1 at 20% retention, with 61.9% contradiction precision.

A **second** correction followed. The first attempt at the new gold misread set-valued relations:
random deletion removes individual list members and leaves the container behind, so a shrunken
prerequisite list was treated as authoritative and true-but-deleted facts became gold
"contradictions". That produced a published claim that the proposed route over-abstains, recovering
only 14.2% of detectable contradictions. **That claim is withdrawn** — the system was right and the
answer key was wrong. Actual contradiction recall is 94.6–100%. The invariant "gold must never label
a reference-world truth as Contradicted" is now a test.

## Main findings

**1. A third label is necessary but not sufficient — measured across 15 models and four vendors.**
Without it, every model lands at 68.1–73.9% harm regardless of capability (a 5.8-point spread over a
10× capability range), so the binary failure is a property of the task. With it, harm drops 1.4×–14.3×
depending entirely on the model, and **no model reaches zero**: best 5.1% (CI [0.8, 10.8], excluding
zero), median 24.3%.

**2. The failure mode is uniformly under-abstention.** Abstention precision is 97.2–100% for every
model — when a model says "I cannot tell", it is essentially always right. The entire spread comes
from abstention recall (26.7%–93.3%). Models never abstain when they shouldn't; they fail to abstain
when they should.

**3. Correct abstention does not track capability.** Spearman(competence, harm) = −0.66, but
within-tier spread (48.9 points) is ~4× the between-tier spread (13.2 points), and the ordering is
non-monotonic inside every vendor. `gpt-5.4-nano` — the smallest model in its family — is the best
abstainer in the panel and beats frontier `gpt-5.5` fourfold. Waiting for better models is not a
strategy.

**4. Stale completeness metadata is worth nothing.** On the convention-free safety metric,
`declared_stale` and `binary` score **identically** — 66.4% at 20% retention, matching in all four
generator/detector pairings at every retention level. A completeness field that is not re-derived
when the data changes has the safety profile of no field at all.

**5. The symbolic verifier is not the bottleneck.** Oracle linking and verification are both 100%,
and Stage 4 on correctly extracted atoms is 100% for every model pairing, while end-to-end
expected-triple F1 ranges 98.6% → 79.7%. The error budget is dominated by claim extraction.

**6. Oracle context is optimistic by a measurable amount.** A real BM25 retriever over all 11,647
records achieves 88.0% recall@1 when the query carries a course code and 47.0% when it carries only
the title, against the oracle arm's assumed 100%.

## The metric that matters

**Contradiction rate on true claims (CR-true)** — of the claims that are true in the reference world,
how many did the system call `Contradicted`? This needs no convention about how absence should be
labelled, so it survives disagreement with our design choices. False-contradiction rate is retained
only for comparability with prior work.

One caveat is stated everywhere it applies: `declared_oracle` receives a declaration regenerated for
the exact damage applied, so it *cannot* emit a false contradiction. Its zero is a **ceiling, not a
result**.

## What retention means

`100/95/90/80/50/20%` are nominal **relation-fact retention** targets. All 11,647 module nodes remain
in every graph — we delete facts *about* modules, never modules. `80%` means roughly 80% of credit,
school, prerequisite, preclusion, and offered-semester facts remain and roughly 20% are deleted.
Clustered department deletion can depart from the nominal value; manifests record the realized rate.

The percentages are unrelated to accuracy, confidence, or two-pass decomposition agreement.

## Pipeline

1. Generate long-form answers under closed-book, full graph-context, or degraded graph-context.
2. Decompose each answer twice and retain normalized claims that agree across passes.
3. Link subjects and objects with exact IDs, labels, dense similarity, and NIL rejection.
4. Normalize schema-gated relation phrases and recover embedded institutional values.
5. Verify triples with relation-specific symbolic logic.
6. Route absence through declarations (fresh or stale), occupancy inference, or binary collapse.
7. Save row-level outputs, hashes, usage, errors, and clustered-bootstrap analyses.

Confidence is heuristic. The calibration experiment is diagnostic and provides no conformal or
deployment-safety guarantee.

## Repository map

- `verification_pipeline.py`: decomposition, linking, relation mapping, verification, aggregation.
- `kg_store.py`: isolated graph stores, declarations, and cached occupancy.
- `scripts/intervention_gold.py`: **declaration-independent gold**; read its module docstring first.
- `data/completeness_declarations/`: explicit dataset relation status.
- `scripts/build_degraded_graphs.py`: random/clustered deletion with logs and manifests.
- `scripts/run_incompleteness_pilot.py`: answer generation, decomposition, mapping, pilot output.
- `scripts/rescore_incompleteness_sweep.py`: deterministic multi-seed/multi-retention rescore.
- `scripts/rescore_external_baselines.py`: re-scores saved LLM/MiniCheck predictions under new gold.
- `scripts/analyze_stage_attribution.py`: oracle and end-to-end stage ceilings.
- `scripts/run_flat_context_incompleteness.py`: oracle-context LLM baseline.
- `scripts/run_model_panel.py` / `scripts/analyze_model_panel.py`: the 15-model, four-vendor panel.
- `scripts/evaluate_retrieval_recall.py`: BM25 retrieval recall bounding the oracle-context arm.
- `scripts/run_minicheck_incompleteness.py`: pinned MiniCheck baseline.
- `scripts/run_benchmark_sweep.py`: isolated public-transfer cells and process manifest.
- `experiments/registry.json`: current machine-readable evidence ledger.

## Verify the checkout

```bash
.venv/Scripts/python.exe -m pip install -r requirements-experiments.txt
```

```bash
.venv/Scripts/python.exe -m unittest discover -s tests
```

Expected result: **183 tests pass**.

Deterministic graph-destruction gates also pass: 34.76% mean shuffled prediction change on NUSMods
and 29.53% on CoDEx, both above the required 20% threshold. The rescore reports **5 residual gold
anomalies** across 61,164 scored rows — all from one multi-hop triple — which is the self-check
confirming that every degraded graph is a pure deletion of the reference graph.

## Documentation

- [Current status](docs/CURRENT_STATUS.md)
- [Comprehensive final study](docs/benchmarks/comprehensive_final_study_20260803.md)
- [Methodology of record](docs/architecture/methodology.md)
- [Benchmark construction](docs/benchmark_construction.md)
- [Experiment runbook](docs/experiment_runbook.md)

Artifacts produced under the old declaration-coupled gold remain on disk for forensic comparison but
are not current evidence. Any table showing a flat 0.0% false-contradiction rate for a system named
plain `declared`, or a 1.000 macro-F1, comes from those files and is withdrawn.
