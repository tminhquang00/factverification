# Documentation

Start with [`CURRENT_STATUS.md`](CURRENT_STATUS.md). It is the one-page answer to what is built,
what has been run, what the retention percentages mean, and what can currently be claimed.

## Active documents

| Document | Purpose |
| --- | --- |
| [`CURRENT_STATUS.md`](CURRENT_STATUS.md) | Single current implementation and research status |
| [`benchmarks/comprehensive_final_study_20260803.md`](benchmarks/comprehensive_final_study_20260803.md) | Complete experiment results, analysis, limitations, and publication assessment |
| [`architecture/methodology.md`](architecture/methodology.md) | Implemented pipeline and evaluation methodology |
| [`benchmark_construction.md`](benchmark_construction.md) | Current graph, question, degradation, and mechanical-gold construction |
| [`experiment_runbook.md`](experiment_runbook.md) | Reproduction commands and artifact checks |

The machine-readable study ledger is
[`experiments/registry.json`](../experiments/registry.json).

## Status vocabulary

- `validated_engineering`: supported by deterministic tests or controls.
- `candidate_automated`: completed automated research evidence with stated validity limits.
- `superseded`: historical output that must not be cited as current.
- `not_established`: a claim the current study cannot support.

No current research result is labelled independently validated because the final study intentionally
omits human review. Engineering tests and graph-destruction controls can still be validated within
their deterministic scope.

## Cleanup policy

The docs tree contains one current result report and no separate implementation-status journals,
draft papers, pilot reports, or duplicate dataset guides. Removed files remain recoverable through
Git history. Historical experiment outputs may remain on disk for forensic comparison, but only the
artifacts named by `CURRENT_STATUS.md` and the registry are current evidence.
