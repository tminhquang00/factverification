# Architecture

**Updated:** 2026-07-26

Four documents, split by whether they describe **what the system does** or **what it was designed to
do**. That distinction was previously blurred, and several components documented here as working were
never built — so it is now enforced by file.

## Describes the built system

| Document | Read it for |
| --- | --- |
| **[methodology.md](methodology.md)** | **Start here.** The architecture-of-record: pipeline stages with their real algorithms and parameters, the evaluation protocol, instrumentation rules, and the methodology's own limitations. |
| [system_expert_review.md](system_expert_review.md) | Code-level reference: call ordering, fallback chains, thresholds, and a table of everything previously documented but not implemented. |
| [system_explained_v3.md](system_explained_v3.md) | Plain-language walkthrough, no notation. Good for orienting a new reader or a non-technical reviewer. |

## Describes the intended system

| Document | Read it for |
| --- | --- |
| [design.md](design.md) | The design roadmap: verification-oriented ontology (Part II), harness specification (Part V), dataset inventory (Part VI), and the contribution claims. Carries a build-status map — **much of it is unbuilt.** |

---

## The three facts most often gotten wrong

Stated here because each was documented incorrectly for a period, and each changes how results
should be read.

1. **Routing uses *occupancy*, not completeness.** `estimate_relation_occupancy` is the fraction of
   records in the *currently loaded* graph with a field populated. It says nothing about whether the
   graph covers the world. The completeness estimator in [design.md](design.md) is not built.
2. **Confidence is uncalibrated, and there is no NLI component anywhere.** No fitted mapping to
   correctness exists, no calibration split is collected, and no false-alarm rate is controlled.
   Coverage and selective accuracy are descriptive statistics at one operating point.
3. **Offline `C(R)` profiles are dead code.** `data/completeness_profiles/*.json` are read only by
   `Catalog2Adapter`; `VerificationPipeline` never consults them.

## The governing acceptance test

Accuracy that does not move when the graph's factual content is destroyed is not verification.

```powershell
& .venv\Scripts\python.exe -m scripts.run_kg_destruction_control --entity_link_threshold 0.95
```

This exits non-zero if fewer than 20% of predictions change under a structure-preserving shuffle of
the graph's values. Any change to Stages 3–4 must keep it passing. It read 1.8–2.8% before the
object-namespace repair and reads 28.9% now.
