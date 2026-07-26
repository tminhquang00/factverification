# NUSMods: a non-circular institutional-catalog tri-state benchmark

**Date:** 2026-07-26 · **Status:** candidate · **Registry:** `nusmods_institutional_benchmark`

> [!NOTE]
> This is the **construction reference** — data provenance, graph schema, label convention, and
> reproduction. The full study, with both engines, the ablation suite, paired significance tests,
> and the cross-dataset comparison, is
> [nusmods_study_20260726.md](nusmods_study_20260726.md). The single-engine results below are
> superseded by that paper's tables.

---

## 1. Why this benchmark exists

README §2 records claim **C4** (post-hoc verification is deployable on closed institutional
catalogs) as *not supported*, for two reasons. One is calibration, which this benchmark does not
address. The other is that the existing institutional benchmark is **circular**: `eval_rmit.py:54`
verifies a template interpolated from the fields the verifier queries, over a 219-course graph, so
it measures template round-tripping rather than catalog verification.

NUSMods addresses the second problem and the scale problem:

| | RMIT | NUSMods |
|:---|---:|---:|
| Entities | 219 | **11,647** |
| Source | scraped handbook | NUS public API, 6 academic years |
| Label derivation | template interpolated from queried fields | see §3 |
| Majority-class floor | 41.67% | **33.80%** |
| Closed-book LLM accuracy | not measured | **33.80%** (= the floor) |

It does **not** address calibration. Confidence remains uncalibrated (`confidence_calibrated:
false`), so nothing here is a risk guarantee, and the false-contradiction rate is measured but not
*controlled*.

---

## 2. Data and graph construction

`scripts/download_nusmods.py` pulls `moduleInformation.json` for AY2020-21 through AY2025-26 from
the NUSMods v2 API (`https://api.nusmods.com/v2`). `scripts/parse_nusmods.py` compiles the union —
11,647 unique modules, each kept at its most recent academic year — into `data/nusmods_graph.json`,
plus `data/nusmods_graph.ttl` and the occupancy profile.

The graph is emitted in the field names `KGStore` and `VerificationPipeline` already dispatch on,
so NUSMods runs through the same explicit stage-4 branches RMIT does rather than through the
open-domain relation-normalization fallback:

| Ontology relation | Graph field | Source field | Measured occupancy |
|:---|:---|:---|---:|
| `hasCreditValue` | `credits` | `moduleCredit` | 1.0000 |
| `partOfSchool` | `school` | `faculty` | 1.0000 |
| `requiresPrerequisite` | `prerequisites` | `prerequisite` (free text) | 0.3119 |

Two construction decisions carry validity weight.

**Absent fields are omitted, never written empty.** `KGStore.estimate_relation_occupancy` counts a
relation as present whenever the key exists and the value is not `""`/`None`/`"Unknown"` — an empty
list passes that test. Writing `"prerequisites": []` for the 69% of modules that declare none would
report prerequisite occupancy as 1.00 instead of 0.31 and pin a mostly-blank relation to
closed-world semantics. `tests/test_nusmods_benchmark.py` asserts no field is written empty.

**`prerequisites` holds every module named in the rule, alternatives included.** The API exposes
prerequisites as free text ("must have completed 1 of CS1010/CS1010E/CS1101S"), not as a tree. The
extracted list is therefore the set of modules the rule *mentions*, not a conjunction, and a claim
built on it reads as "X is named as a prerequisite option of Y". `data/rmit_graph.json` encodes the
same thing. Prerequisite rules that name retired codes the catalog no longer carries are excluded
from item construction: such a row is unverifiable by construction, since the object cannot be
linked whatever the verifier does.

---

## 3. Label convention: world-assumption independence

Every gold label is **independent of the CWA/OWA routing decision**. This is the design constraint
the generator follows from.

* **Supported** — the catalog states the claimed value.
* **Contradicted** — the catalog states a *conflicting* value for the same single-valued attribute
  (credits, faculty), or the claim asserts "no prerequisites" for a module whose record names some.
  A conflict is a conflict under either assumption.
* **Not-in-KG** — the subject module is absent from the catalog entirely, so no assumption about
  relation completeness can produce a verdict.

**Deliberately excluded:** claims of the form "module A requires module B" where A exists, has a
prerequisite rule, and B is not in it. Prerequisite occupancy is 0.31, so the correct label there
genuinely depends on whether the relation is read closed- or open-world. Including such items would
make the benchmark score a routing *choice* rather than a fact — the same defect that makes
`eval_rmit.py` circular. The consequence is that **this benchmark cannot evaluate claim C1**
(world-assumption routing); it is deliberately blind to it.

### Composition (n = 500, seed 20260726)

| Reasoning type | n | Labels |
|:---|---:|:---|
| `credit-one-hop` | 109 | Supported / Contradicted |
| `school-one-hop` | 92 | Supported / Contradicted |
| `absent-module-credit` | 66 | Not-in-KG |
| `absent-module-school` | 58 | Not-in-KG |
| `prerequisite-negation` | 50 | Supported / Contradicted |
| `conjunction` | 42 | Supported / Contradicted |
| `absent-module-prerequisite` | 41 | Not-in-KG |
| `prerequisite-one-hop` | 34 | Supported |
| `prerequisite-multi-hop` | 8 | Supported |

Labels: Supported 169, Contradicted 166, Not-in-KG 165. **Majority-class floor 33.80%.**

Hard negatives are drawn from the catalog's own value distributions, weighted by frequency — a
`Contradicted` credit row claims 5 MCs for a 4-MC module, not 54. The previous generator used
`true_credits + 50`, which any "implausibly large number is false" prior classifies correctly
without consulting the graph at all. Absent-module codes use real department prefixes but differ
from every same-prefix real code in at least two digit positions, so they read as plausible without
sitting inside the entity linker's noise band.

Each row carries two triple fields, and the distinction matters:

* `triples` — the graph's evidence for the subject. This is what the `context_llm` baseline is
  shown. On a `Contradicted` row it holds the **true** edge.
* `asserted_triples` — what the sentence states. On a `Contradicted` row it holds the **false**
  edge.

Collapsing them, as `data/codex_test.jsonl` does, hands the context baseline the answer.

---

## 4. Validity controls

### 4.1 Stage-3/4 ceiling and entity-link threshold

`scripts/diagnose_nusmods_stage4.py` feeds `asserted_triples` straight into stages 3–4 with no LLM.
Whatever it reports is the upper bound the full pipeline can reach, so every point below it in an
end-to-end run is attributable to stage-2 decomposition.

| `entity_link_threshold` | Accuracy | Supported recall | Contradicted recall | Not-in-KG recall |
|---:|---:|---:|---:|---:|
| 0.35 (default) | 0.7520 | 1.000 | 1.000 | **0.248** |
| 0.60 | 0.7520 | 1.000 | 1.000 | **0.248** |
| 0.95 | **1.0000** | 1.000 | 1.000 | 1.000 |

Below 0.95 the bi-encoder links non-existent module codes to real modules and the `Not-in-KG` class
collapses — `absent-module-credit` and `absent-module-school` score 0/66 and 0/58 at the default
threshold. NUSMods runs therefore use `--entity_link_threshold 0.95`, the same value
`scripts/sweep_entity_threshold.py` selected for CoDEx. The ceiling of 1.0000 means no item is
unverifiable by construction; it also means the benchmark's difficulty lives entirely in
decomposition and linking, not in graph lookup.

### 4.2 Graph-destruction control — **PASS**

`scripts/run_kg_destruction_control.py --benchmark nusmods` preserves graph structure (entity set,
relation keys, per-relation value multiset) and destroys only the subject–value association.

| Condition | Accuracy | Predictions changed |
|:---|---:|---:|
| baseline | 1.0000 | — |
| shuffled, seed 11 | 0.7120 | 0.2880 |
| shuffled, seed 23 | 0.7000 | 0.3000 |
| shuffled, seed 37 | 0.7160 | 0.2840 |
| relations removed | 0.3640 | 0.6360 |

Mean prediction change under shuffle **0.2907**, against an acceptance gate of 0.20. Verdicts are
attributable to the graph's factual content, not to surface form or label priors.

Note the scaffolding set differs by benchmark. On CoDEx, `credits`/`school`/`prerequisites` are
unused scaffolding and are protected from the shuffle; on NUSMods those three fields *are* the
facts under test, so protecting them would make the control shuffle nothing and pass vacuously.

---

## 5. Results

Engine `google/gemma-4-e4b` (local), n = 500, random sampling under seed 20260725,
`--entity_link_threshold 0.95`. Every cell reports zero unscored rows.

| Method | Accuracy | 95% CI | Coverage | Selective acc. | Calls/row | Tokens/row |
|:---|---:|:---:|---:|---:|---:|---:|
| `closed_book_llm` | 33.80% | [29.80%, 38.00%] | — | — | 1.00 | 268 |
| `context_llm` | 72.00% | [68.00%, 75.60%] | — | — | 1.00 | 329 |
| **`pipeline`** | **99.40%** | [98.60%, 100.00%] | 100.00% | 99.40% | 2.00 | 863 |

Per-class, pipeline: Supported P 100.00 / R 98.22, Contradicted P 98.22 / R 100.00, Not-in-KG
P 100.00 / R 100.00.

**The closed-book baseline scores exactly the majority-class floor.** It answers `Not-in-KG` for
essentially every row (Not-in-KG recall 1.000 at precision 0.333, Supported recall 0.024,
Contradicted recall 0.000). A 4B model has no memorised knowledge of the NUS catalog, so the task
is not solvable from priors — which, with the destruction control, is the case that the pipeline's
99.40% is coming from the graph.

### Per-reasoning-type, pipeline vs. context baseline

| Reasoning type | n | Pipeline | `context_llm` |
|:---|---:|---:|---:|
| `absent-module-credit` | 66 | 100.00% | 100.00% |
| `absent-module-prerequisite` | 41 | 100.00% | 100.00% |
| `absent-module-school` | 58 | 100.00% | 100.00% |
| `conjunction` | 42 | 97.62% | 73.81% |
| `credit-one-hop` | 109 | 100.00% | 55.05% |
| `prerequisite-multi-hop` | 8 | 100.00% | 12.50% |
| `prerequisite-negation` | 50 | 100.00% | 60.00% |
| `prerequisite-one-hop` | 34 | 100.00% | 100.00% |
| `school-one-hop` | 92 | 97.83% | 42.39% |

The separation is concentrated exactly where structured lookup should help: value comparison
(`credit-one-hop`, `school-one-hop`), set-emptiness (`prerequisite-negation`), and path traversal
(`prerequisite-multi-hop`, where the same model with flat triple context scores 12.5%).

### The three pipeline errors

All three are faculty-name surface mismatches, all in the `Supported → Contradicted` direction:

* `SPH5314` — graph holds `SSH School of Public Health`; the claim's object decomposed to a
  different surface form.
* `TIE4212`, `TCE5107` — graph holds `Cont and Lifelong Education`, an abbreviation the model
  expands when extracting the object.

`normalize_text` strips a leading `faculty of` (added for this benchmark, symmetric with the
existing `school of` / `department of` handling), but it does not expand catalog abbreviations, and
it should not: doing so would make the comparison tolerant in a way the graph cannot justify.

---

## 6. What this does and does not establish

**Establishes.** The verification path is graph-grounded on an 11.6k-entity institutional catalog
(destruction control, 29.1% prediction change). The task is not solvable from LLM priors
(closed-book = the majority floor). Structured verification beats a same-model flat-context
baseline by **+27.4 points**, concentrated in comparison and traversal. `Not-in-KG` is a live class
here rather than a collapsed one, but only above an entity-link threshold of 0.95.

**Does not establish.**

1. **Supported items remain template-derived.** Their *content* is interpolated from the same
   fields the verifier queries. Phrasing is varied per item (4 credit templates, 4 faculty, 3
   prerequisite, 3 negation, 2 multi-hop, 3 conjunction), so a `Supported` item tests decomposition
   and linking rather than a single surface pattern — but it does not test catalog comprehension.
   This is a weaker form of the RMIT circularity, not its absence.
2. **The headline is near ceiling.** At 99.40% against a stage-3/4 ceiling of 100.00%, the benchmark
   discriminates poorly between competent systems. Its value is the controls and the baseline
   separation, not the headline number.
3. **Nothing about C1.** World-assumption-sensitive items are excluded by design (§3).
4. **Nothing about calibration.** Confidence is uncalibrated; coverage of 100% at this operating
   point is a descriptive statistic, not a risk guarantee.
5. **One engine.** Only `google/gemma-4-e4b` was run. The `azure-4.1-mini` cell is registered in
   `scripts/run_benchmark_sweep.py` but has not been executed.

---

## 7. Reproduction

```powershell
# 1. Fetch the catalog (already present under data/nusmods/)
& .venv\Scripts\python.exe scripts\download_nusmods.py

# 2. Compile the graph, TTL, and occupancy profile
& .venv\Scripts\python.exe scripts\parse_nusmods.py

# 3. Generate the benchmark (deterministic under --seed)
& .venv\Scripts\python.exe scripts\build_nusmods_benchmark.py --limit 500 --seed 20260726

# 4. Regression tests (17 NUSMods tests; 77 total in the suite)
& .venv\Scripts\python.exe -m unittest discover -s tests

# 5. Stage-3/4 ceiling and entity-link threshold selection — no LLM, seconds
& .venv\Scripts\python.exe -m scripts.diagnose_nusmods_stage4 --thresholds 0.35 0.60 0.95 `
    --out output\diagnostics\nusmods_stage4_ceiling.json

# 6. Grounding gate — fails if predictions survive destroying the graph's content
& .venv\Scripts\python.exe -m scripts.run_kg_destruction_control --benchmark nusmods `
    --entity_link_threshold 0.95 --out output\diagnostics\nusmods_destruction_control.json

# 7. End-to-end, one arm per method
& .venv\Scripts\python.exe eval_harness.py --dataset nusmods --method pipeline --limit 500 `
    --provider local --model_name google/gemma-4-e4b --max_workers 8 `
    --entity_link_threshold 0.95 --sample random `
    --output_file output\experiments\nusmods_20260726\nusmods__gemma_4_e4b__pipeline.json
```

Artifacts: `output/experiments/nusmods_20260726/` (row-level predictions for all three methods),
`output/diagnostics/nusmods_stage4_ceiling.json`,
`output/diagnostics/nusmods_destruction_control.json`.
