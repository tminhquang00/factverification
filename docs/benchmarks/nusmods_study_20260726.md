# Structured Claim Verification against an Institutional Course Catalog: A Tri-State Benchmark over 11,647 NUS Modules

**Study date:** 2026-07-26 · **Status:** candidate · **Registry:** `nusmods_institutional_benchmark`
**Artifacts:** `output/experiments/nusmods_20260726/`, `output/diagnostics/nusmods_*.json`

---

## Abstract

We introduce **NUSMods**, a tri-state claim-verification benchmark built over the complete public
course catalog of the National University of Singapore (11,647 modules, six academic years), and
evaluate a four-stage post-hoc verification pipeline on it alongside four existing benchmarks
(FactKG, CoDEx, MetaQA, RMIT). The benchmark is constructed so that **every gold label is
independent of the closed-world/open-world routing decision**, which removes the circularity that
invalidates the study's existing institutional benchmark, where the verified string is a template
interpolated from the very fields the verifier queries.

Three results are load-bearing. First, structured verification against the catalog reaches
**99.80%** (azure-4.1-mini) and **99.40%** (google/gemma-4-e4b) against a 33.80% majority-class
floor, and passes a graph-destruction control at 29.07% prediction change. Second, and more
interesting than the headline, **the pipeline erases the engine gap**: the two engines differ by
18.80 points when each is given flat triple context (90.80% vs 72.00%, paired McNemar
$p = 9.5\times10^{-24}$) but by 0.40 points inside the pipeline (99.80% vs 99.40%, $p = 0.625$,
not significant). A 4B model running locally matches a hosted frontier-class model once the graph
does the comparison. Third, the pipeline's advantage over a strong flat-context baseline is
**concentrated in reasoning a triple list cannot express** — set-emptiness ("this module has no
prerequisites": 100% vs 66%) and multi-hop traversal — rather than in value lookup.

A fourth result is negative and concerns the benchmark this one replaces. Running RMIT's
`--verify_field text` arm on all 300 rows shows the pipeline returning `Out-of-scope` with zero
decomposed claims on 50.67% of them, because RMIT's `text` field holds a *question*, not an
assertion. RMIT therefore contains **no natural-language claim in either field**, its circularity
cannot be quantified by switching fields, and the recommendation carried in three prior reports —
"verify `text` rather than `raw_claim`" — is not implementable as written.

We also report what the benchmark does not establish: it sits at its own stage-3/4 ceiling and so
discriminates poorly between competent systems; its `Supported` items remain template-derived; it
is deliberately blind to the world-assumption routing claim; and confidence remains uncalibrated,
so no false-contradiction rate is *controlled*.

---

## 1. Introduction

### 1.1 The problem with the existing institutional benchmark

The study's target claim **C4** is that post-hoc claim-level verification is deployable on closed
institutional catalogs with a controlled false-contradiction rate. Its evidence was an RMIT course
handbook benchmark of 219 courses. That benchmark has a construct-validity defect: the string
submitted for verification (`raw_claim`) is a template interpolated from the graph's own field
names, so the verifier is asked to confirm a sentence assembled out of the values it is about to
look up. Accuracy on it measures template round-tripping. The harness now exposes the defect
directly through `--verify_field {raw_claim,text}`; §8.5 measures the gap.

The defect turns out to be worse than "accuracy is inflated". §8.5 shows RMIT contains **no
natural-language assertion at all** — its two fields are the interpolated template and a *question*,
and a question gives an assertion verifier nothing to check. The circularity cannot be removed by
switching fields; it requires authoring claims whose surface form does not derive from graph field
names.

A second, subtler defect affects any tri-state benchmark built on a knowledge graph. If a gold
label is assigned by asking "is this fact in the graph?" for a relation the graph populates only
sometimes, then the correct label depends on whether that relation is read closed-world (absence
means false) or open-world (absence means unknown) — which is precisely the policy the verifier is
configured with. Such a benchmark scores the verifier's configuration, not its accuracy.

### 1.2 Contributions

1. **A non-circular institutional benchmark at scale.** 11,647 modules against RMIT's 219, drawn
   from a public API rather than a scrape, with a label convention proved world-assumption
   independent by regression test (§4.3, §6.4).
2. **A stage-3/4 ceiling diagnostic** that separates decomposition error from graph-handling error
   with no LLM in the loop, and doubles as the entity-link threshold selector (§6.2).
3. **A graph-destruction control for institutional graphs**, generalizing the existing CoDEx
   control to graphs where credits/faculty/prerequisites are the facts under test rather than
   scaffolding (§6.1).
4. **The engine-gap result** (§9.1): structure substitutes for model capability on this task.
5. **A localization of where structure helps** (§9.2): closed-world set reasoning, not lookup.
6. **A paired statistical protocol.** All ablation arms score identical rows, so arms are compared
   by exact McNemar test on discordant pairs rather than by overlapping confidence intervals.

---

## 2. The benchmark landscape this sits in

| Benchmark | Entities | Test rows | Classes | Majority floor | Defect of record |
|:---|---:|---:|:---|---:|:---|
| FactKG | — (per-row context) | 9,041 | binary | 51.35% | reasoning types are label-confounded (§9.4) |
| CoDEx | 1,189 | 1,000 | tri-state | 33.40% | open-domain; entity linking dominates |
| MetaQA | 35 | 228 | tri-state | 44.74% | too small for 500-row cells |
| RMIT | 50 | 300 | tri-state | 41.67% | verifies its own template; no NL assertion exists (§8.5) |
| **NUSMods** | **11,647** | **500** | **tri-state** | **33.80%** | **template-derived `Supported` content (§10)** |

FactKG's binary protocol is the reason the study needs tri-state benchmarks at all: it collapses
`Not-in-KG`, `Out-of-scope`, and `Abstained` into `Contradicted`, which makes abstention
unmeasurable by construction. §9.4 shows its reasoning types are additionally near-perfectly
label-confounded.

---

## 3. System under evaluation

The verifier is a four-stage post-hoc pipeline (`verification_pipeline.py`). Only stages 2–4 are
exercised here; stage 1 (draft generation) is bypassed because the benchmark supplies the claim.

* **Stage 2 — claim decomposition.** An LLM decomposes the sentence into atomic
  `(subject, relation, object)` claims under a schema-guided system prompt naming the valid
  relation classes. Run twice at temperatures 0.1 and 0.2; claims surviving both runs are kept, and
  the agreement rate is recorded. (Graphs under 50 entities take a single-run fast path; NUSMods
  does not.)
* **Stage 3 — entity and relation resolution.** Subjects are linked by exact key lookup, then by
  bi-encoder cosine similarity (`all-MiniLM-L6-v2`) over an index of codes, titles, and
  code+title strings. A link below `entity_link_threshold` is reported **unresolved** rather than
  snapped to the nearest neighbour. Objects are returned in the graph's own value namespace
  (surface labels), not as entity keys.
* **Stage 4 — dispatched verification.** Each triple is evaluated against `KGStore`. Value
  relations compare directly; set relations check membership and a 2-hop path; absent values
  dispatch on the world assumption, which under `routing_mode=dynamic` is chosen per relation by
  comparing live relation occupancy against `cwa_threshold` (default 0.85).
* **Verdict combination.** `Contradicted` > `Not-in-KG` > `Out-of-scope` > `Supported`. Claims
  whose subject could not be linked are recorded but, by default, still vote; the
  `--withhold_unresolved_claims` arm changes this (§8.3).

**Confidence is uncalibrated.** `calculate_confidence` returns a heuristic product of occupancy,
linking score, and decomposition agreement, with no fitted mapping to correctness. Every result row
carries `confidence_calibrated: false`. Coverage and selective accuracy below are descriptive
statistics at one operating point and are never risk guarantees.

---

## 4. Data

### 4.1 Provenance

| Dataset | Source | Snapshot | Graph | Test set |
|:---|:---|:---|:---|:---|
| NUSMods | NUSMods v2 API (`api.nusmods.com/v2`) | AY2020-21 … AY2025-26 | `data/nusmods_graph.json` | `data/nusmods_test.jsonl` |
| CoDEx | CoDEx-S/M (Wikidata) | as converted | `data/codex_graph.json` | `data/codex_test.jsonl` |
| MetaQA | MetaQA KG | as converted | `data/metaqa_graph.json` | `data/metaqa_test.jsonl` |
| FactKG | FactKG (DBpedia) | as converted | per-row context | `data/factkg_test.jsonl` |
| RMIT | RMIT course handbook scrape | 2026-07 | `data/rmit_graph.json` | `data/rmit_test_set.jsonl` |

### 4.2 NUSMods graph construction

`scripts/download_nusmods.py` fetches `moduleInformation.json` for six academic years.
`scripts/parse_nusmods.py` compiles the union — each module kept at its most recent year — into a
graph emitted in the field names `KGStore` and stage 4 already dispatch on, so NUSMods runs through
the same explicit branches RMIT does rather than through the open-domain relation-normalization
fallback.

| Ontology relation | Graph field | NUSMods source field | Measured occupancy |
|:---|:---|:---|---:|
| `hasCreditValue` | `credits` | `moduleCredit` | 1.0000 |
| `partOfSchool` | `school` | `faculty` | 1.0000 |
| `requiresPrerequisite` | `prerequisites` | `prerequisite` (free text) | 0.3119 |
| — | `department` | `department` | 1.0000 |
| — | `preclusions` | `preclusion` (free text) | 0.3981 |
| — | `semesters` | `semesterData[].semester` | 1.0000 |

Two construction decisions carry validity weight.

**Absent fields are omitted, never written empty.** `KGStore.estimate_relation_occupancy` counts a
relation as present whenever the key exists and the value is not `""`/`None`/`"Unknown"` — an empty
list satisfies that test. Writing `"prerequisites": []` for the 69% of modules that declare none
would report prerequisite occupancy as 1.00 instead of 0.31 and pin a mostly-blank relation to
closed-world semantics. A regression test asserts no field is written empty.

**`prerequisites` holds every module named in the rule, alternatives included.** The API exposes
prerequisites as free text ("must have completed 1 of CS1010/CS1010E/CS1101S"), not as a tree, so
the extracted list is the set of modules the rule *mentions*, not a conjunction. Claims built on it
read as "X is named as a prerequisite option of Y" — the same semantics `data/rmit_graph.json`
encodes. Rules naming retired codes the catalog no longer carries are excluded from item
construction: such a row is unverifiable by construction, since the object cannot be linked
whatever the verifier does.

### 4.3 Label convention: world-assumption independence

* **Supported** — the catalog states the claimed value.
* **Contradicted** — the catalog states a *conflicting* value for the same single-valued attribute
  (credits, faculty), or the claim asserts "no prerequisites" for a module whose record names some.
  A conflict is a conflict under CWA and OWA alike.
* **Not-in-KG** — the subject module is absent from the catalog entirely, so no assumption about
  relation completeness can produce a verdict.

**Deliberately excluded:** claims of the form "module A requires module B" where A exists, has a
prerequisite rule, and B is not in it. Prerequisite occupancy is 0.31, so the correct label there
genuinely depends on the routing policy. Including such items would make the benchmark score a
routing *choice* rather than a fact. The consequence is stated plainly: **this benchmark cannot
evaluate claim C1 (world-assumption routing) and is deliberately blind to it.** §8.2 confirms the
design empirically — forcing either fixed assumption leaves accuracy unchanged.

### 4.4 Composition ($n = 500$, seed 20260726)

| Reasoning type | $n$ | Labels represented |
|:---|---:|:---|
| `credit-one-hop` | 109 | Supported, Contradicted |
| `school-one-hop` | 92 | Supported, Contradicted |
| `absent-module-credit` | 66 | Not-in-KG |
| `absent-module-school` | 58 | Not-in-KG |
| `prerequisite-negation` | 50 | Supported, Contradicted |
| `conjunction` | 42 | Supported, Contradicted |
| `absent-module-prerequisite` | 41 | Not-in-KG |
| `prerequisite-one-hop` | 34 | Supported |
| `prerequisite-multi-hop` | 8 | Supported |

Labels: Supported 169, Contradicted 166, Not-in-KG 165 — **majority-class floor 33.80%**.

Hard negatives are drawn from the catalog's own value distributions, weighted by frequency: a
`Contradicted` credit row claims 5 MCs for a 4-MC module, not 54. (The generator this replaced used
`true_credits + 50`, which an "implausibly large number is false" prior classifies correctly
without consulting the graph at all.) Absent-module codes use real department prefixes but differ
from every same-prefix real code in at least two digit positions, so they read as plausible without
sitting inside the entity linker's noise band. No module appears in two items.

Each row carries two triple fields, and the distinction matters: `triples` is the graph's evidence
for the subject and is what the `context_llm` baseline is shown — on a `Contradicted` row it holds
the **true** edge — while `asserted_triples` is what the sentence states. Collapsing them, as
`data/codex_test.jsonl` does, hands the context baseline the answer.

---

## 5. Experimental setup

### 5.1 Configuration

| Factor | Value |
|:---|:---|
| Engines | `azure-4.1-mini` (hosted), `google/gemma-4-e4b` (local, LM Studio) |
| Methods | `pipeline`, `context_llm` (gold triples supplied), `closed_book_llm` (no graph) |
| $n$ per cell | 500 (the full benchmark) |
| Sampling | `random`, seed 20260725 — identical rows in every cell |
| `entity_link_threshold` | 0.95 (selected in §6.2) |
| `routing_mode` | `dynamic`, `cwa_threshold` 0.85 |
| Decomposition | 2 runs, temperatures 0.1 / 0.2, self-consistency filtered |
| Parallelism | 8 worker threads |

### 5.2 Scoring rules

* **A crash is not a prediction.** Rows whose evaluation raised are recorded with `pred: None` and
  excluded from the denominator, rather than defaulted to a class label. Every cell in this study
  reports **zero** unscored rows.
* **Tri-state is scored alongside the collapse.** `coverage` is the share of rows receiving a
  decisive raw verdict (`Supported`/`Contradicted`/`Not-in-KG`); `Out-of-scope` counts as
  abstention. `selective_accuracy` is accuracy on the covered subset.
* **Every aggregate is recomputed from row-level predictions** by
  `scripts/analyze_nusmods_results.py`; stored values are compared against the recomputation and a
  disagreement is reported. None occurred.

### 5.3 Statistical protocol

Confidence intervals are 2,000-sample percentile bootstraps over scored rows under a fixed seed.

Because every arm scores identical rows, arms are **paired**. Comparisons therefore use an exact
McNemar test on the $b + c$ discordant pairs (reference-only-correct vs arm-only-correct) under
$\text{Binomial}(b+c, 0.5)$. Comparing two independent confidence intervals would be the wrong
test on paired data: overlapping intervals do not imply a difference is inside the noise floor, and
disjoint intervals overstate the evidence.

---

## 6. Validity controls

These were run **before** the results in §7, and two of them are gates.

### 6.1 Graph-destruction control — PASS

`scripts/run_kg_destruction_control.py --benchmark nusmods` preserves graph structure (entity set,
relation keys, per-relation value multiset) and destroys only the subject–value association.
Accuracy that survives destruction is not verification.

| Condition | Accuracy | Predictions changed |
|:---|---:|---:|
| baseline | 1.0000 | — |
| shuffled, seed 11 | 0.7120 | 0.2880 |
| shuffled, seed 23 | 0.7000 | 0.3000 |
| shuffled, seed 37 | 0.7160 | 0.2840 |
| relations removed | 0.3640 | 0.6360 |

Mean prediction change **0.2907** against an acceptance gate of 0.20 → **PASS**. For comparison,
the same control on CoDEx gives 0.2895 (and gave 0.018–0.028 before the stage-3 object-namespace
repair, i.e. the pipeline was then *not* graph-grounded).

The scaffolding set differs by benchmark: on CoDEx, `credits`/`school`/`prerequisites` are unused
scaffolding and are protected from the shuffle; on NUSMods those three fields *are* the facts under
test, so protecting them would make the control shuffle nothing and pass vacuously.

### 6.2 Stage-3/4 ceiling and threshold selection

`scripts/diagnose_nusmods_stage4.py` feeds `asserted_triples` directly into stages 3–4 with no LLM.
The result is the upper bound the full pipeline can reach, so end-to-end shortfall is attributable
to stage 2.

| `entity_link_threshold` | Accuracy | Supported R | Contradicted R | Not-in-KG R |
|---:|---:|---:|---:|---:|
| 0.35 (library default) | 0.7520 | 1.000 | 1.000 | **0.248** |
| 0.60 | 0.7520 | 1.000 | 1.000 | **0.248** |
| **0.95** | **1.0000** | 1.000 | 1.000 | 1.000 |

Below 0.95 the bi-encoder links non-existent module codes to real modules and the `Not-in-KG` class
collapses (`absent-module-credit` 0/66, `absent-module-school` 0/58). All main cells therefore use
0.95, the same value `scripts/sweep_entity_threshold.py` selected on a held-out CoDEx split.

A ceiling of 1.0000 means **no item is unverifiable by construction**. It also means the
benchmark's difficulty lives entirely in decomposition and linking, which §10 treats as a
limitation rather than a strength.

### 6.3 Routing non-vacuity

`scripts/diagnose_routing_occupancy.py` reports whether `cwa_threshold` can change any decision.

| Graph | Entities | Relations | Saturated at 0/1 | Interior | Distinct routings over $\tau \in [0.5, 0.95]$ |
|:---|---:|---:|---:|---:|---:|
| RMIT | 50 | 7 | 7 | 0 | 1 (uninformative) |
| catalog2 | 100 | 5 | 5 | 0 | 1 (uninformative) |
| MetaQA | 35 | 6 | 3 | 3 | 4 |
| CoDEx | 1,189 | 25 | 2 | 23 | 4 |
| **NUSMods** | **11,647** | **7** | **5** | **2** | **1 (uninformative)** |

NUSMods' two interior relations (`preclusions` 0.398, `requiresPrerequisite` 0.312) both sit below
0.5, so sweeping $\tau$ over $[0.5, 0.95]$ is a flat line on this graph. Sweeping `cwa_threshold`
here would measure nothing, and was not run. The `fixed_cwa` / `fixed_owa` arms *are* informative
because they override the per-relation decision entirely (§8.2).

### 6.4 Benchmark self-consistency

`tests/test_nusmods_benchmark.py` (17 tests, part of the 77-test suite) asserts the properties the
labels depend on: every `Supported` assertion is entailed by the graph; every `Contradicted`
assertion conflicts with a value the graph *holds* (not merely absent — this is the
world-assumption-independence proof); every `Not-in-KG` subject is absent from the catalog; context
triples differ from asserted triples on every `Contradicted` row; no module appears twice; the
majority floor stays below 0.40; and generation is deterministic under its seed.

---

## 7. Results

### 7.0 Figures

Regenerate with `python -m scripts.plot_nusmods_results --dir output/experiments/nusmods_20260726`.

| Figure | File | Shows |
|:---|:---|:---|
| 1 | `analysis/01_method_comparison.png` | Accuracy by method × engine with bootstrap CIs and the majority floor (§7.1) |
| 2 | `analysis/02_entity_link_threshold.png` | LLM-free ceiling vs. end-to-end accuracy across the link threshold (§6.2, §8.1) |
| 3 | `analysis/03_reasoning_type.png` | Per-construction accuracy, pipeline vs. flat-context baseline (§7.3, §9.2) |
| 4 | `analysis/04_ablation_deltas.png` | Paired deltas for every ablation arm with McNemar $p$ (§8) |

### 7.1 NUSMods headline

$n = 500$, identical rows in every cell, zero unscored rows.

| Engine | Method | Accuracy | 95% CI | Macro-F1 | Coverage | Selective acc. |
|:---|:---|---:|:---:|---:|---:|---:|
| azure-4.1-mini | closed-book | 41.00% | [36.20%, 45.40%] | 0.3211 | — | — |
| azure-4.1-mini | context | 90.80% | [88.00%, 93.20%] | 0.9098 | — | — |
| **azure-4.1-mini** | **pipeline** | **99.80%** | [99.40%, 100.00%] | **0.9980** | 99.80% | **100.00%** |
| gemma-4-e4b | closed-book | 33.80% | [29.20%, 38.00%] | 0.1820 | — | — |
| gemma-4-e4b | context | 72.00% | [68.00%, 75.80%] | 0.7103 | — | — |
| **gemma-4-e4b** | **pipeline** | **99.40%** | [98.60%, 100.00%] | **0.9940** | 100.00% | **99.40%** |

Majority-class floor 33.80%.

**Paired tests** (exact McNemar, same 500 rows):

| Comparison | Δ | ref-only correct | arm-only correct | flip rate | $p$ |
|:---|---:|---:|---:|---:|---:|
| pipeline vs context, gemma | **+27.40** | 3 | 140 | 28.60% | $8.7\times10^{-38}$ |
| pipeline vs context, azure | **+9.00** | 1 | 46 | 9.40% | $6.8\times10^{-13}$ |
| pipeline vs closed-book, gemma | +65.60 | 0 | 328 | 66.20% | $3.7\times10^{-99}$ |
| **azure vs gemma, pipeline** | **+0.40** | 1 | 3 | 0.80% | **0.625 (n.s.)** |
| azure vs gemma, context | +18.80 | 5 | 99 | 21.20% | $9.5\times10^{-24}$ |

### 7.2 Per-class

| Engine / method | Supported P / R | Contradicted P / R | Not-in-KG P / R |
|:---|:---|:---|:---|
| azure, pipeline | 1.000 / 0.994 | 1.000 / 1.000 | 0.994 / 1.000 |
| gemma, pipeline | 1.000 / 0.982 | 0.982 / 1.000 | 1.000 / 1.000 |
| azure, context | 1.000 / 0.817 | 1.000 / 0.910 | 0.782 / 1.000 |
| gemma, context | 0.891 / 0.722 | 0.961 / 0.440 | 0.575 / 1.000 |
| azure, closed-book | 0.537 / 0.130 | 0.833 / 0.121 | 0.375 / 0.988 |
| gemma, closed-book | 0.800 / 0.024 | 0.000 / 0.000 | 0.333 / 1.000 |

Both context baselines have **perfect `Not-in-KG` recall and poor `Not-in-KG` precision** — given a
triple list they over-abstain, converting `Supported` and `Contradicted` rows into "insufficient
information". The pipeline does not, because absence of a *subject* and absence of a *value* are
different states in stage 4.

### 7.3 Per item construction

Accuracy by reasoning type, all four graph-informed cells:

| Reasoning type | $n$ | azure pipe | gemma pipe | azure ctx | gemma ctx |
|:---|---:|---:|---:|---:|---:|
| `absent-module-credit` | 66 | 100.0% | 100.0% | 100.0% | 100.0% |
| `absent-module-prerequisite` | 41 | 100.0% | 100.0% | 100.0% | 100.0% |
| `absent-module-school` | 58 | 100.0% | 100.0% | 100.0% | 100.0% |
| `conjunction` | 42 | 100.0% | 97.6% | 100.0% | 73.8% |
| `credit-one-hop` | 109 | 100.0% | 100.0% | 97.3% | 55.1% |
| `prerequisite-multi-hop` | 8 | 87.5% | 100.0% | 87.5% | 12.5% |
| **`prerequisite-negation`** | 50 | **100.0%** | **100.0%** | **66.0%** | **60.0%** |
| `prerequisite-one-hop` | 34 | 100.0% | 100.0% | 97.1% | 100.0% |
| `school-one-hop` | 92 | 100.0% | 97.8% | 73.9% | 42.4% |

### 7.4 Cross-dataset context

The authoritative public-benchmark sweep (`rerun_20260726_cleangraph`, all aggregates recomputed
from row-level predictions, zero unscored rows) sits alongside NUSMods as follows.

| Dataset | Engine | Sampling | $n$ | Accuracy | 95% CI | Floor | Macro-F1 | Coverage | Sel. acc. |
|:---|:---|:---|---:|---:|:---:|---:|---:|---:|---:|
| **NUSMods** | azure-4.1-mini | random | 500 | **99.80%** | [99.4, 100.0] | 33.80% | 0.998 | 99.8% | 100.0% |
| **NUSMods** | gemma-4-e4b | random | 500 | **99.40%** | [98.6, 100.0] | 33.80% | 0.994 | 100.0% | 99.4% |
| RMIT | azure-4.1-mini | full | 300 | 97.33% | [95.3, 99.0] | 41.67% | 0.989 | 97.3% | 100.0% |
| RMIT | gemma-4-e4b | full | 300 | 89.00% | [85.7, 92.3] | 41.67% | 0.906 | 94.3% | 94.4% |
| CoDEx | azure-4.1-mini | random | 500 | 83.00% | [79.4, 86.2] | 34.60% | 0.830 | 100.0% | 83.0% |
| CoDEx | azure-4.1-mini | prefix | 500 | 82.20% | [78.8, 85.6] | 36.40% | 0.824 | 100.0% | 82.2% |
| CoDEx | gemma-4-e4b | random | 500 | 77.40% | [73.6, 80.8] | 34.60% | 0.777 | 92.4% | 80.7% |
| CoDEx | gemma-4-e4b | prefix | 500 | 75.80% | [71.8, 79.6] | 36.40% | 0.762 | 92.0% | 79.1% |
| FactKG | azure-4.1-mini | prefix | 500 | 83.20% | [80.0, 86.2] | 64.60% | 0.816 | 61.6% | 76.3% |
| FactKG | azure-4.1-mini | random | 500 | 58.20% | [54.0, 62.4] | 52.80% | 0.503 | 71.6% | 58.7% |
| FactKG | gemma-4-e4b | prefix | 500 | 81.40% | [78.0, 85.0] | 64.60% | 0.785 | 47.2% | 84.3% |
| FactKG | gemma-4-e4b | random | 500 | 56.60% | [52.0, 60.6] | 52.80% | 0.461 | 62.4% | 59.9% |

> **Read the sampling column.** `data/factkg_test.jsonl` is sorted into contiguous reasoning-type
> blocks, so `prefix` selects 2 of 13 reasoning types at a 64.60% majority floor against the full
> set's 51.35%. The two FactKG arms differ by ~25 points on identical code. §9.4 explains why.

Ranking the datasets by *margin over floor* rather than raw accuracy: NUSMods +66.0 (azure),
CoDEx +48.4, RMIT +55.7, FactKG +5.4 (random) / +18.6 (prefix).

### 7.5 Cost and latency

Measured per row, all cells $n = 500$.

| Cell | Calls/row | Tokens/row | Latency mean | Latency p95 |
|:---|---:|---:|---:|---:|
| NUSMods, azure, pipeline | 2.00 | 838 | 1.76 s | 5.56 s |
| NUSMods, azure, context | 1.00 | 304 | 1.90 s | 6.71 s |
| NUSMods, azure, closed-book | 1.00 | 245 | 1.85 s | 6.81 s |
| NUSMods, gemma, pipeline | 2.00 | 863 | 3.41 s | 4.40 s |
| NUSMods, gemma, context | 1.00 | 329 | 4.18 s | 6.13 s |
| CoDEx, azure, pipeline | 2.00 | 409 | 1.84 s | 6.54 s |
| RMIT, azure, pipeline | 2.00 | 791 | 2.37 s | 7.59 s |
| FactKG, azure, pipeline (random) | 1.59 | 729 | 2.69 s | 7.74 s |

The pipeline costs **2.8×** the tokens of the context baseline (838 vs 304) for +9.00 points on
azure and **2.6×** (863 vs 329) for +27.40 points on gemma. The two decomposition calls dominate;
stages 3–4 are LLM-free. Read against §9.1, the token premium buys engine-independence: the local
engine at 863 tokens/row and zero marginal API cost reaches within 0.40 points of the hosted model.

---

## 8. Ablation study

All arms score the same 500 rows as the reference (gemma, pipeline, $\tau_{\text{link}} = 0.95$,
dynamic routing), so every comparison is paired and tested by exact McNemar.

**Summary.** One knob matters and the rest do not:

| Arm | Accuracy | Δ | Rows changed | $p$ |
|:---|---:|---:|---:|---:|
| link threshold → 0.35 | 74.40% | **−25.00** | 125 | $4.7\times10^{-38}$ |
| link threshold → 0.60 | 74.40% | **−25.00** | 125 | $4.7\times10^{-38}$ |
| link threshold → 0.35 (azure) | 74.80% | **−24.60** | 129 | $1.1\times10^{-33}$ |
| routing → fixed CWA | 99.20% | −0.20 | 1 | 1.000 |
| routing → fixed OWA | 99.40% | 0.00 | **0** | 1.000 |
| withhold unresolved claims | 99.20% | −0.20 | 1 | 1.000 |
| replicate (same seed) | 99.40% | 0.00 | **0** | 1.000 |
| engine → azure-4.1-mini | 99.80% | +0.40 | 4 | 0.625 |

The two −0.20 rows are the *same* row and are noise, not effects (§8.4).

### 8.1 Entity-link rejection threshold

| Arm | Engine | Accuracy | Δ vs 0.95 | Not-in-KG recall | $p$ |
|:---|:---|---:|---:|---:|---:|
| $\tau = 0.95$ (reference) | azure | 99.80% | — | 1.000 | — |
| $\tau = 0.35$ | azure | **74.80%** | **−25.00** | **0.249** | $1.1\times10^{-33}$ |
| $\tau = 0.95$ (reference) | gemma | 99.40% | — | 1.000 | — |
| $\tau = 0.35$ | gemma | **74.40%** | **−25.00** | **0.248** | $4.7\times10^{-38}$ |
| $\tau = 0.60$ | gemma | **74.40%** | **−25.00** | **0.248** | $4.7\times10^{-38}$ |

The $\tau = 0.35$ and $\tau = 0.60$ arms are **identical row-for-row** (both lose the same 125 rows
and gain none), matching the LLM-free sweep where 0.35 and 0.60 also tie at 0.7520. The collapse
boundary lies somewhere in $(0.60, 0.95]$; a finer sweep would locate it, but the operating point
is already the top of the range. The degradation is one-directional — 125 losses, 0 gains — so it
is a class deletion, not a reshuffling.

The end-to-end drop is **−25.00 points on both engines**, and it tracks the LLM-free ceiling drop
(−24.80 points, §6.2) almost exactly. That correspondence localizes the failure to stage 3 rather
than to any interaction with decomposition, and it is why the threshold is selected on the
deterministic diagnostic rather than by spending API budget.

Per-construction, both $\tau = 0.35$ arms score **0/66** on `absent-module-credit` and **0/58** on
`absent-module-school` while remaining at 100% on `credit-one-hop` (azure) and 100% (gemma) — the
threshold does not degrade verification, **it deletes one class**.

**This is the single most consequential hyperparameter in the study.** The library default of 0.35
is a historical value; on any graph large enough that a fabricated identifier has a near neighbour,
it silently converts "this entity does not exist" into "this entity has the wrong value".

### 8.2 World-assumption routing — the design claim, tested

§4.3 asserts that every gold label is independent of the CWA/OWA decision. That is a falsifiable
claim about the benchmark, and this arm tests it: forcing every relation to one assumption should
change nothing. Engine gemma-4-e4b, all else held at the reference configuration.

| Routing mode | Accuracy | Δ | Rows changed | $p$ |
|:---|---:|---:|---:|---:|
| `dynamic` (reference) | 99.40% | — | — | — |
| `fixed_cwa` | 99.20% | −0.20 | **1 / 500** | 1.000 |
| `fixed_owa` | 99.40% | 0.00 | **0 / 500** | 1.000 |

**The claim survives, and more cleanly than the table shows.** Forcing open-world semantics on
every relation changes not one prediction. `fixed_cwa` changes a single row — `nus-0417`,
"EC3304 is listed among the prerequisites of EC4304HM", which moves `Supported → Not-in-KG`.

That row is **not** a routing effect. Re-running the claim in isolation under `dynamic`,
`fixed_cwa`, and `withhold_unresolved_claims` returns `Supported` in all three cases, with the same
mapped triple `(EC4304HM, requiresPrerequisite, EC3304)` verified `Supported` under both an open
and a closed world assumption. The row is decomposition-unstable (§8.4), and the same row flips the
same way in the unrelated §8.3 arm. **The true effect of forcing either world assumption on this
benchmark is zero rows out of 500.**

Two things follow. First, §4.3's construction is validated empirically, not only by regression
test. Second, **NUSMods cannot be used to evaluate C1** — a benchmark on which the routing knob
moves no rows has no power to distinguish routing policies. That is by design, and it must not be
mistaken for evidence that routing does not matter in general; on a graph whose labels are *not*
assumption-independent the same knob decides the verdict for every absent value.

### 8.3 Unresolved-claim voting

`--withhold_unresolved_claims` withholds a claim whose subject could not be linked from the verdict
vote, on the grounds that it carries no evidence.

| Arm | Accuracy | Δ | Rows changed | $p$ |
|:---|---:|---:|---:|---:|
| off (default) | 99.40% | — | — | — |
| on | 99.20% | −0.20 | 1 / 500 | 1.000 |

The one row is `nus-0417` again — the same decomposition-unstable item as §8.2, and likewise not
attributable to the flag: in isolation the arm returns `Supported`, and the claim's subject links
at score 1.0, so the withholding rule never fires on it. **The measured effect is zero rows.**

This is expected: the flag only acts when subject linking fails, and at $\tau = 0.95$ on a catalog
of exact-matchable codes that does not happen. It is consistent with the prior measurement of
+0.8 points on CoDEx (inside its noise floor) against −2.67 on RMIT; the flag remains off by
default, and NUSMods provides no evidence either way.

### 8.4 Run-to-run variance

Four arms re-execute stage-2 decomposition under a configuration that cannot change stage 2 (a
same-seed replicate, plus the three arms of §8.2–8.3, which alter only stage-4 dispatch and vote
aggregation). Their flip counts against the reference therefore estimate run-to-run
nondeterminism directly:

| Re-execution | Rows changed vs. reference |
|:---|---:|
| same-seed replicate | 0 / 500 |
| `fixed_owa` | 0 / 500 |
| `fixed_cwa` | 1 / 500 |
| `withhold_unresolved_claims` | 1 / 500 |

**Estimated flip rate 0.10% (2 flips over 2,000 row-executions), concentrated in a single row.**
Both flips are the same item, `nus-0417`, whose decomposition is unstable; isolated re-runs of it
return `Supported` under every configuration. Every other row reproduced exactly across all four
re-executions.

This is a property of this engine on this benchmark, not a general noise floor — the claims are
short and syntactically regular, and the local runtime at temperature 0.1/0.2 is close to
deterministic on them. The comparable CoDEx figure is a 7.2% flip rate.

Two consequences for reading the rest of the study. First, the −0.20 point deltas in §8.2 and §8.3
are **noise, not small effects**: they are the same unstable row, and the flags do not touch it.
Second, the 4 discordant rows behind the +0.40 engine delta in §7.1 sit well above this floor, so
they are reproducible differences between the two models rather than sampling jitter — genuine, but
at $b = 1$, $c = 3$ far too few to assign a direction ($p = 0.625$). **"Equivalent within
measurement" is the correct reading; "identical" is not.**

### 8.5 The RMIT circularity gap is not measurable on RMIT

`eval_rmit.py --verify_field {raw_claim,text}` was run on identical rows, gemma-4-e4b, $n = 300$,
zero unscored rows.

| Arm | Accuracy | 95% CI |
|:---|---:|:---:|
| `raw_claim` (interpolated template) | 89.67% | [85.67%, 93.00%] |
| `text` (the other field) | **45.33%** | [40.00%, 51.00%] |

Paired: 134 rows correct only under `raw_claim`, 1 only under `text`, 50.67% flip rate,
$p = 6.2\times10^{-39}$.

**This 44.33-point drop is not the circularity gap, and reporting it as one would be wrong.**
RMIT's `text` field holds a *question*, not an assertion:

```
text      : "How many credit points is Course 053802 (Computational Machine Learning) worth?"
raw_claim : "Course 053802 (Computational Machine Learning) is worth 12 credit points."
```

A question carries no proposition, so an assertion verifier has nothing to check. The verdict
distribution confirms this directly: **152 of 300 rows (50.67%) return `Out-of-scope` with zero
decomposed claims** — the pipeline correctly refuses — and are scored as errors only because the
benchmark has no gold label for "there is no claim here". On the 148 rows where a claim *was*
extractable, accuracy is **91.89%**, slightly *above* the `raw_claim` arm's 89.67%.

The correct conclusion is stronger than an inflation estimate and worse for RMIT: **the benchmark
offers no natural-language assertion at all.** Its two fields are a template that round-trips the
graph's own field names and a question that contains no claim. The circularity therefore cannot be
quantified by switching fields; de-circularizing RMIT requires authoring natural-language responses
whose surface form does not derive from graph field names, which is what NUSMods does (§4.4) and
what the registry records as `rmit_text_field_is_a_question_not_a_response` (status `defect_open`).

This run extends that finding from the 3 rows previously spot-checked to all 300 under a paired
test, and it revises the standing recommendation carried in three prior reports — "verify `text`
rather than `raw_claim`" — which is not implementable as written.

---

## 9. Analysis

### 9.1 Structure substitutes for model capability

The two engines are 18.80 points apart when each is handed flat triple context
($p = 9.5\times10^{-24}$) and 0.40 points apart inside the pipeline ($p = 0.625$, not significant;
4 discordant pairs out of 500). The pipeline's accuracy is therefore **not** a property of the
language model — it is a property of the graph plus the dispatch logic, with the LLM reduced to a
decomposition front-end that a 4B local model performs as well as a hosted one.

This is the most deployment-relevant result in the study. An institution running catalog
verification can do so on-premise, at zero marginal API cost and no data egress, without paying the
accuracy penalty that the same model incurs in a retrieval-augmented prompt.

The caveat is scope: it holds on a three-relation ontology with exact-matchable identifiers. CoDEx,
whose open-domain ontology has 23 interior relations, still shows a 5.6-point engine gap
(83.00% vs 77.40%).

### 9.2 The advantage lives in closed-world set reasoning, not lookup

Decomposing the +9.00-point pipeline-over-context margin on azure by construction:

| Construction | Margin | Interpretation |
|:---|---:|:---|
| `prerequisite-negation` | **+34.0** | "has no prerequisites" — a *closed-world* assertion about an empty set |
| `school-one-hop` | +26.1 | value comparison over 26 faculty labels |
| `credit-one-hop` | +2.7 | value comparison over a small integer range |
| `absent-module-*` | 0.0 | both methods already perfect |
| `prerequisite-one-hop` | +2.9 | set membership |

The gap is dominated by set-emptiness. A flat triple context can state what *is* true; it cannot
state that a set is empty, so the baseline reads a missing prerequisite edge as "insufficient
information" and returns `Not-in-KG` for a claim the catalog supports. Stage 4 handles this with an
explicit branch: it queries the prerequisite set, finds it empty, and — because the subject exists
— returns `Supported`. **The pipeline's advantage is the ability to distinguish "the graph says
nothing" from "the graph says nothing is there."**

The second-largest contribution is faculty comparison (+26.1), where the baseline must judge
whether "SSH School of Public Health" and "School of Public Health" denote the same unit, while
stage 4 applies a deterministic normalization.

### 9.3 The tri-state protocol makes "admitting ignorance" visible

`azure-4.1-mini` scores 41.00% closed-book against a 33.80% floor. That margin is not knowledge of
the NUS catalog — its `Supported` recall is 0.130 and `Contradicted` recall 0.121. It is
**calibrated ignorance**: `Not-in-KG` recall is 0.988, so the model reliably identifies fabricated
module codes it has never seen. `gemma-4-e4b` answers `Not-in-KG` on 495 of 500 rows and scores
exactly the floor.

Under a binary protocol both behaviours would be scored identically (both collapse to
`Contradicted`), and the stronger model's genuine skill — knowing what it does not know — would be
invisible. This is direct support for claim **C3**: binary fact-verification benchmarks cannot
evaluate abstention-capable verifiers.

Neither closed-book arm has usable knowledge of the catalog, which, with §6.1, is the case that the
pipeline's 99%+ comes from the graph.

### 9.4 FactKG's reasoning types are label-confounded

The sampling artifact in §7.4 has a measurable cause. Per reasoning type in the full 9,041-row set:

| Reasoning type | $n$ | $P(\text{Contradicted})$ |
|:---|---:|---:|
| `num2\|substitution` | 1,247 | **0.9936** |
| `num1\|substitution` | 856 | **0.9918** |
| `num3\|substitution` | 828 | **0.9940** |
| `num4\|substitution` | 555 | **0.9730** |
| `num2` | 1,126 | **0.0089** |
| `num1` | 1,058 | **0.0038** |
| `num3` | 731 | **0.0082** |
| `num4` | 456 | **0.0110** |
| `existence` | 870 | 0.5241 |
| `negation\|num1` | 462 | 0.5823 |

A constant-`Contradicted` predictor scores 0.99 on `num2|substitution` and 0.01 on `num2` — two
types that differ only by whether a substitution was applied. Because the file is sorted into
contiguous type blocks, prefix sampling selects a subpopulation whose label prior is 64.60%, and
accuracy measured on it is not comparable to accuracy on a random draw. **FactKG accuracy is not
interpretable without its sampling protocol**, and reported FactKG numbers that do not state one
should be treated as unlabelled.

NUSMods is stratified across constructions by design (§4.4) and is shuffled before writing, so
prefix and random sampling draw from the same distribution.

---

## 10. Threats to validity

1. **`Supported` items remain template-derived.** Their content is interpolated from the same
   fields the verifier queries. Phrasing is varied per item (4 credit templates, 4 faculty, 3
   prerequisite, 3 negation, 2 multi-hop, 3 conjunction), so a `Supported` item tests decomposition
   and linking rather than one surface pattern — but it does not test catalog comprehension. This
   is a weaker form of the RMIT circularity, not its absence.
2. **The headline is at the ceiling.** 99.80% against a stage-3/4 ceiling of 100.00% leaves 1
   error. The benchmark cannot rank competent systems; it can only detect broken ones. Its
   discriminative power lives in the ablation arms (§8.1 moves 25 points) and the baseline
   contrasts, not the headline.
3. **Three relations.** The ontology is credits, faculty, prerequisites. Catalog attributes with
   messier surface forms — workload tuples, assessment structures, exam dates — are in the graph
   but not in the benchmark.
4. **Prerequisite semantics are approximated.** The API's free-text rules encode disjunction and
   grade conditions that regex extraction flattens to a mention set (§4.2). Claims are true in the
   "named as an option" sense, which is weaker than "is required".
5. **Blind to C1.** World-assumption-sensitive items are excluded by construction.
6. **Uncalibrated confidence.** No calibration split was collected; coverage and selective accuracy
   are descriptive at one operating point. **No false-contradiction rate is controlled**, so claim
   C4 is only partially supported even with this benchmark.
7. **Single snapshot, single institution.** One catalog, fetched 2026-07-26. Generalization to
   other institutions' catalogs is untested.
8. **Two engines, one local runtime.** `gemma-4-e4b` numbers depend on the LM Studio quantization
   in use, which is not pinned in the artifact.

---

## 11. What may and may not be claimed

**May be claimed.**

* The verification path is graph-grounded on an 11.6k-entity institutional catalog (§6.1).
* The task is not solvable from LLM priors (§7.1, §9.3).
* Structured verification beats a same-model flat-context baseline by +9.00 points (azure) and
  +27.40 points (gemma), both significant under a paired test (§7.1).
* Inside the pipeline the engine gap is not significant, while outside it the same two engines
  differ by 18.80 points (§9.1).
* The advantage is concentrated in closed-world set reasoning (§9.2).
* The entity-link rejection threshold governs whether `Not-in-KG` exists as a class (§6.2, §8.1).
* RMIT's `text` field is not a verification task; its circularity is not removable by field
  switching (§8.5, all 300 rows, paired).

**May not be claimed.**

* **That RMIT accuracy is inflated by 44 points.** The `raw_claim`-vs-`text` drop is dominated by
  correct abstention on rows that contain no claim; on rows where a claim was extractable the two
  arms are within noise (§8.5). The circularity remains unquantified.

* That the pipeline "achieves 99.8% on institutional catalogs" without stating the ceiling, the
  three-relation ontology, and the template derivation of `Supported` items.
* Any risk guarantee, error rate under deployment, or calibration property.
* Anything about world-assumption routing (C1) from this benchmark.
* That NUSMods is harder than CoDEx — it is substantially easier; it is *cleaner*, not harder.

---

## 12. Reproduction

```powershell
# Data -> graph -> benchmark (deterministic under --seed)
& .venv\Scripts\python.exe scripts\download_nusmods.py
& .venv\Scripts\python.exe scripts\parse_nusmods.py
& .venv\Scripts\python.exe scripts\build_nusmods_benchmark.py --limit 500 --seed 20260726

# Gates and diagnostics (no LLM, seconds)
& .venv\Scripts\python.exe -m unittest discover -s tests            # 77 tests
& .venv\Scripts\python.exe -m scripts.diagnose_nusmods_stage4 --thresholds 0.35 0.60 0.95 `
    --out output\diagnostics\nusmods_stage4_ceiling.json
& .venv\Scripts\python.exe -m scripts.run_kg_destruction_control --benchmark nusmods `
    --entity_link_threshold 0.95 --out output\diagnostics\nusmods_destruction_control.json
& .venv\Scripts\python.exe -m scripts.diagnose_routing_occupancy `
    --json output\diagnostics\routing_occupancy_with_nusmods.json

# Main cells (repeat per engine/method)
& .venv\Scripts\python.exe eval_harness.py --dataset nusmods --method pipeline --limit 500 `
    --provider azure --model_name azure-4.1-mini --max_workers 8 `
    --entity_link_threshold 0.95 --sample random `
    --output_file output\experiments\nusmods_20260726\nusmods__azure_4_1_mini__pipeline.json

# Recompute every aggregate from row-level predictions, with paired McNemar tests
& .venv\Scripts\python.exe -m scripts.analyze_nusmods_results `
    --dir output\experiments\nusmods_20260726 `
    --out output\experiments\nusmods_20260726\analysis_summary.json
& .venv\Scripts\python.exe -m scripts.plot_nusmods_results --dir output\experiments\nusmods_20260726
```

**Artifacts.** Row-level predictions for every cell in
`output/experiments/nusmods_20260726/` (main) and `.../ablation/`; recomputed aggregates and paired
tests in `analysis_summary.json`; figures in `analysis/`; diagnostics in
`output/diagnostics/nusmods_*.json` and `routing_occupancy_with_nusmods.json`.
