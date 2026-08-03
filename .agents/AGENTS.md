---
description: "Use when orienting to this repository for the first time in a session, or when a task touches the overall pipeline, evaluation harness, adapters, or benchmark scripts and it's unclear how the pieces fit together. Provides a research-project overview: purpose, architecture, terminology, and key files for the KG fact-verification framework."
---

# Codebase Overview: KG Fact-Verification Framework

This is a **research codebase**, not a production service. Expect experimental/one-off scripts in `scratch/` and result dumps in `output/` alongside the core library — prioritize reproducibility and correctness of experiments over production hardening (e.g. it's fine for scratch scripts to be ad hoc, but core pipeline/adapters/store code should stay correct and consistent with published benchmark numbers).

## What it does

Implements a 4-stage **tri-state** claim verification pipeline that checks natural-language assertions against Knowledge Graphs (KGs), using local or remote LLMs:

1. **Claim decomposition** — draft LLM answers are broken into atomic `(Subject, Relation, Object)` tuples.
2. **Entity/relation linking** — resolved via **L0** (gold IDs), **L1** (bi-encoder), or **L2** (token heuristics).
3. **Graph verification** — triples checked against explicit per-relation completeness declarations; live relation occupancy is retained as an ablation.
4. **Tri-state output** — final verdict is one of `Supported` / `Contradicted` / `Not-in-KG` (plus `Out-of-scope`). Confidence remains heuristic and uncalibrated; no NLI component exists.

## Key files

- [verification_pipeline.py](../verification_pipeline.py) — core 4-stage pipeline.
- [kg_store.py](../kg_store.py) — thread-safe local KG/catalog storage, relation density estimation.
- [adapters/](../adapters/) — per-dataset loaders/normalizers (`factkg_adapter.py`, `codex_adapter.py`, `metaqa_adapter.py`, `fever_adapter.py`, `catalog2_adapter.py`, `kg_adapter.py`).
- [eval_harness.py](../eval_harness.py), [eval_rmit.py](../eval_rmit.py) — evaluation entry points.
- [scripts/](../scripts/) — diagnostics, staged experiments (E0–E9), completeness-profile and tri-state benchmark generation.
- [docs/](../docs/) — start at [docs/README.md](../docs/README.md); architecture in `docs/architecture/`, results in `docs/benchmarks/`.

## Benchmarks in play

Institutional catalogs (**RMIT Handbook**, **Catalog2**) plus public KG benchmarks (**FactKG**, **CoDEx-S**, **MetaQA**). **FEVER/Climate-FEVER** are text-evidence only and excluded from structured graph verification (reported as `N/A`).

## Related

For coding-style, evaluation-protocol, and execution rules (e.g. venv usage, confidence-interval requirements, forced-decision label normalization), see [.agents/AGENTS.md](AGENTS.md) — those always apply and are not repeated here.
