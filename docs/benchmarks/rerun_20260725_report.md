# Rerun 2026-07-25 — Run Log

> [!IMPORTANT]
> **The authoritative write-up is [`rerun_20260725_paper.md`](rerun_20260725_paper.md).**
> This file is retained only as a chronological log of what was executed. It carries no results
> tables, so that there is exactly one citable source for every number.

## Timeline

| Phase | Artifact directory | Outcome |
| --- | --- | --- |
| Pre-fix sweep | `output/experiments/rerun_20260725/` | Completed, but FactKG cells invalidated by the stage-3 defect |
| Defect found, reproduced, repaired | `verification_pipeline.py`, `tests/test_verification_pipeline.py` | Suite 23 → 25 tests, all passing |
| Post-fix sweep | `output/experiments/rerun_20260725_fixed/` | **Primary results.** Zero crashes in all six cells |

## Pre-fix sweep (superseded)

Ten jobs: RMIT (n=300), FactKG (n=500), CoDEx (n=500) × {`azure-4.1-mini`, `azure-5-mini`,
`gemma-4-e4b`}, plus the deterministic graph-destruction control.

* `azure-4.1-mini` and `gemma-4-e4b` cells completed.
* `azure-5-mini` RMIT and FactKG completed; its CoDEx job was cancelled at user request, and
  `azure-5-mini` was dropped from the study scope. Its artifacts remain in the pre-fix directory
  and are **not** analysed in the paper.
* FactKG raised `TypeError: 'bool' object is not callable` on 113/500 rows
  (`azure-4.1-mini`) and 30/500 (`gemma-4-e4b`).

## Repair

`verification_pipeline.py` — the boolean flag at line 305 shadowed the `mapped()` helper defined
at line 268, breaking all eleven `return mapped(...)` call sites. Renamed to
`relation_was_mapped`. Added `StageThreeFallbackTests` covering the unclassified-relation fallback.

Full analysis: [`rerun_20260725_paper.md` §5](rerun_20260725_paper.md#5-defect-analysis).

## Post-fix sweep (primary)

Six jobs: RMIT / FactKG / CoDEx × {`azure-4.1-mini`, `gemma-4-e4b`}, plus the control.
All exit codes 0; zero crashes; no previously-masked exception surfaced. Settings identical to the
pre-fix sweep (`--max_workers 1`, `--seed 42` on RMIT, same limits), making the two sweeps a paired
comparison.

Results, methodology, and validity analysis: [`rerun_20260725_paper.md`](rerun_20260725_paper.md).

## Commands

See [`rerun_20260725_paper.md` §11](rerun_20260725_paper.md#11-reproduction).
