# Documentation

Start with [`CURRENT_STATUS.md`](CURRENT_STATUS.md). It is the one-page answer to what is built,
what has been run, what the retention percentages mean, and what can currently be claimed.

> **Gold revision 2026-08-03b.** An earlier headline — that the proposed `declared` route achieved a
> zero false-contradiction rate — has been **withdrawn**. The old gold function read the same
> completeness declaration as the system it was scoring, so the system was graded against its own
> rule and scored a perfect 1.000 in all 336 cells. Gold is now computed from graph contents alone by
> [`scripts/intervention_gold.py`](../scripts/intervention_gold.py). Any table showing a flat 0.0%
> false-contradiction rate for a system named plain `declared`, or a 1.000 macro-F1, predates this
> revision and is not current evidence.

## Active documents

| Document | Purpose |
| --- | --- |
| [`paper/absence_is_not_contradiction.md`](paper/absence_is_not_contradiction.md) | **Paper draft** — contribution, methodology, experiment design, results, analysis, conclusion |
| [`CURRENT_STATUS.md`](CURRENT_STATUS.md) | Single current implementation and research status |
| [`benchmarks/comprehensive_final_study_20260803.md`](benchmarks/comprehensive_final_study_20260803.md) | Complete experiment results, analysis, limitations, and publication assessment |
| [`architecture/methodology.md`](architecture/methodology.md) | Implemented pipeline and evaluation methodology |
| [`benchmark_construction.md`](benchmark_construction.md) | Current graph, question, degradation, and gold-label construction |
| [`experiment_runbook.md`](experiment_runbook.md) | Reproduction commands and artifact checks |

The single most important implementation file to read before trusting any number is
[`scripts/intervention_gold.py`](../scripts/intervention_gold.py). Its module docstring explains what
gold depends on, what it deliberately does not depend on, and which arm of the study is a ceiling
rather than a result.

The machine-readable study ledger is
[`experiments/registry.json`](../experiments/registry.json).

## Status vocabulary

- `validated_engineering`: supported by deterministic tests or controls.
- `candidate_automated`: completed automated research evidence with stated validity limits.
- `superseded`: historical output that must not be cited as current.
- `not_established`: a claim the current study cannot support.
- `withdrawn`: a previously reported claim found to be circular or otherwise unsound, retracted but
  kept discoverable in the registry so the retraction is not lost.

No current research result is labelled independently validated because the final study intentionally
omits human review. Engineering tests and graph-destruction controls can still be validated within
their deterministic scope.

## Cleanup policy

The docs tree contains one current result report and no separate implementation-status journals,
draft papers, pilot reports, or duplicate dataset guides. Removed files remain recoverable through
Git history. Historical experiment outputs may remain on disk for forensic comparison, but only the
artifacts named by `CURRENT_STATUS.md` and the registry are current evidence.
