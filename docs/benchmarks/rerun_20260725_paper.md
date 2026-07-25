# Evaluating a Knowledge-Graph Fact-Verification Pipeline Across Institutional and Public Benchmarks: Data, Methodology, and Results

**Study id:** `rerun_20260725_fixed`
**Run date:** 2026-07-25
**Engines:** `azure-4.1-mini` (Azure OpenAI), `google/gemma-4-e4b` (local, LM Studio)
**Artifacts:** `output/experiments/rerun_20260725_fixed/` (post-fix, primary), `output/experiments/rerun_20260725/` (pre-fix, defect case study)
**Status:** `candidate` — not promoted to `validated`. See [§9](#9-what-may-and-may-not-be-claimed).

---

## Abstract

We evaluate a four-stage knowledge-graph fact-verification pipeline on one institutional
benchmark (RMIT course handbook, *n*=300), two public benchmarks (FactKG *n*=500, CoDEx *n*=500),
and a deterministic set-completeness control, across two LLM engines. The study is primarily an
**evaluation-integrity** result rather than a performance result.

Three findings dominate. First, we identify and repair a name-shadowing defect in the claim-mapping
stage that raised `TypeError` on 22.6% of FactKG rows under `azure-4.1-mini`; because the
evaluation harness converts an exception into the dataset's default label, and that label
coincided with FactKG's majority class, **113 crashes were scored as 111 correct predictions**.
Repairing the defect moved headline accuracy by only 1.2 points (81.4%→80.2%), which we show is a
coincidence of label alignment rather than evidence that the defect was harmless. Second, paired
reruns under identical settings — in cells where the repair is provably unreachable — flip
**2.0–9.6% of individual predictions** (mean 5.75%), establishing a nondeterminism floor
comparable in magnitude to most between-engine differences reported here. Third, on CoDEx the
pipeline has effectively lost one of its three decision classes: `Supported` recall is 0.039 and
0.006 for the two engines at precision 1.000, a failure invisible in the headline accuracy.

We further document that the RMIT benchmark's high accuracy (97.3%) is structurally inflated: the
evaluator verifies a template string interpolated from the same KG fields it subsequently queries.
We report what each artifact can and cannot support.

---

## 1. Introduction

### 1.1 System under evaluation

The system is a post-hoc verifier: given a natural-language statement and a knowledge graph, it
returns one of three verdicts — `Supported`, `Contradicted`, or `Not-in-KG` — plus two
non-decision outcomes, `Out-of-scope` (no claim could be parsed or the relation is outside the
ontology) and, in the harness, `Error` (an exception was raised).

### 1.2 Research questions

* **RQ1 (Grounding).** Do the pipeline's outputs depend on the graph's factual content, or are
  they recoverable from surface form and label priors?
* **RQ2 (Transfer).** Does performance on a closed institutional catalog transfer to public
  KG benchmarks?
* **RQ3 (Abstention).** Does the tri-state design produce useful abstention, and can existing
  binary benchmarks measure it?
* **RQ4 (Measurement validity).** Are the aggregates these harnesses emit faithful to the
  row-level predictions underneath them?

RQ4 was not in the original plan. It became the study's centre of gravity once the defect in
[§5](#5-defect-analysis) was found, and it subsumes the others: RQ1–RQ3 cannot be answered from an
instrument that converts crashes into accuracy.

### 1.3 Contributions

1. A confirmed, reproduced, and repaired implementation defect that silently inflated a published
   benchmark cell, with a quantified before/after comparison ([§5](#5-defect-analysis)).
2. An empirical nondeterminism floor for this evaluation setup, measured by paired reruns in cells
   where the code change is provably unreachable ([§7](#7-run-to-run-reliability)).
3. A per-class analysis showing that CoDEx accuracy conceals total collapse of the `Supported`
   class ([§6.3](#63-codex)).
4. A source-level audit of three circularity and instrumentation problems in the existing
   benchmarks ([§8](#8-threats-to-validity)).
5. Two row-level analysis tools (`scripts/summarize_rerun_results.py`, `scripts/compare_runs.py`)
   that reconstruct every aggregate in this paper from saved predictions.

---

## 2. System Description

### 2.1 Pipeline stages

Implemented in `verification_pipeline.py`.

| Stage | Function | Mechanism |
| --- | --- | --- |
| 2. Decomposition | Statement → atomic claims | LLM, schema-guided prompt; two-pass self-consistency |
| 3. Mapping | Claim → `(subject, relation, object)` | Exact/normalized index lookup, then bi-encoder cosine retrieval |
| 4. Verification | Triple → verdict | Relation-dispatched lookup against `KGStore` under CWA/OWA routing |
| — | Confidence | Composed product (uncalibrated) |

**Stage 3 linking.** `build_entity_index` maps course codes, normalized titles, and code+title
combinations to entity ids. Unresolved surface forms fall back to a `SentenceTransformer`
(`all-MiniLM-L6-v2`) bi-encoder over the entity list, with a TF-IDF character n-gram vectorizer as
a degraded fallback if the model cannot load.

**Stage 4 routing.** `get_world_assumption` selects closed- or open-world semantics per relation.
Under the default `dynamic` mode, a relation whose *occupancy* — the fraction of entity records
with that field populated, `KGStore.estimate_relation_occupancy` — meets `cwa_threshold` (0.85)
is treated as closed-world, so an absent fact yields `Contradicted`; otherwise it yields
`Not-in-KG`. `fixed_cwa` and `fixed_owa` override this. All runs here use `dynamic`.

Note this statistic is *occupancy*, not completeness: it measures how often a field is populated
in the local graph, and carries no information about whether the graph covers the world. The
codebase renamed it accordingly and retains `estimate_relation_completeness` only as an alias.

### 2.2 Two behaviours that materially affect measurement

**Self-consistency is silently disabled on small graphs.** Stage 2 runs decomposition twice (at
temperatures 0.1 and 0.2) and keeps only claims appearing in both, reporting an agreement rate.
But `verification_pipeline.py:230` short-circuits:

```python
if len(self.store.courses) < 50:
    return decomposed(claims1, 1.0)
```

FactKG evaluates each claim against a *transient* per-claim context built from that claim's own
triples (`verify_with_context`), which is always far below 50 entities. **Every FactKG run
therefore performs a single decomposition pass with `decomposition_agreement` hardcoded to 1.0.**
That constant then propagates into the confidence product. RMIT (exactly 50 courses — the
condition is strict `<`) and CoDEx (1,182 entities) do run the two-pass check. Any cross-dataset
comparison of confidence or agreement is confounded by this.

**Confidence is explicitly uncalibrated.** `calculate_confidence` returns
`base_conf × entity_score × decomp_agreement`, where `base_conf` is 1.0 for `Supported`, relation
occupancy for `Contradicted`, and 1−occupancy for `Not-in-KG`. It is a heuristic composition with
no fitted mapping to empirical correctness. Legacy threshold-based abstention is disabled by
default. We report coverage and selective accuracy as *descriptive* statistics at the default
operating point, never as risk guarantees.

---

## 3. Data

### 3.1 Overview

| Dataset | File | Total rows | Used | Graph | Graph size |
| --- | --- | ---: | ---: | --- | ---: |
| RMIT claim set | `data/rmit_test_set.jsonl` | 300 | 300 | `data/rmit_graph.json` | 50 courses |
| FactKG | `data/factkg_test.jsonl` | 9,041 | first 500 | per-claim transient context | varies |
| CoDEx | `data/codex_test.jsonl` | 1,000 | first 500 | `data/codex_graph.json` | 1,182 entities |
| RMIT completeness | `data/advising/rmit_prerequisite_completeness_v0.jsonl` | 181 | 33 (test split) | `data/rmit_graph.json` | 50 courses |

Sampling is by prefix (`data[:limit]`), not random selection. The FactKG and CoDEx subsets are
therefore the *first* 500 rows of each file, and are only representative to the extent those files
are unordered with respect to label and difficulty. This is a preregistration weakness, not a
randomization: no seed governs which rows enter the sample.

### 3.2 Label distributions

| Dataset | Supported | Contradicted | Not-in-KG | Majority floor |
| --- | ---: | ---: | ---: | ---: |
| RMIT (n=300) | 125 | 125 | 50 | 41.67% |
| FactKG (n=500) | 177 | 323 | — | 64.60% |
| CoDEx (n=500) | 155 | 166 | 179 | 35.80% |

FactKG is binary by construction. CoDEx is close to balanced across three classes, which makes its
35.80% floor the most demanding of the three.

### 3.3 RMIT claim set construction — and its circularity

Generated by `generate_dataset.py` from the parsed handbook graph. Six generators produce 50 rows
each: one-hop (credit value), conjunction (prerequisite + school), existence (coordinator +
email), multi-hop (two-step prerequisite chain), negation ("does not require any prerequisites"),
and 50 `Not-in-KG` rows using randomly generated six-digit course codes. The `Not-in-KG` rows are
tagged `reasoning_type = "one-hop"`, which is why the one-hop slice reports *n*=100 in
[§6.2](#62-rmit).

Each record carries two text fields:

* `raw_claim` — a template string interpolated from KG fields, e.g.
  `"Course 038974 (Programming A) is worth 12 credit points."`
* `text` — an LLM paraphrase of that template at temperature 0.7, e.g.
  `"How many credit points is Course 038974 (Programming A) worth?"`

> [!IMPORTANT]
> **`eval_rmit.py:54` verifies `raw_claim`, not `text`.** The paraphrase is generated, stored, and
> never evaluated. The pipeline therefore reads a machine-built sentence whose object value was
> interpolated directly from the field the verifier subsequently looks up. Negative examples are
> produced by deterministic perturbation (`24 if credits == 12 else 12`; school flipped to
> `Business`/`Science`; a hardcoded wrong course id).

This makes the RMIT number a measure of template round-tripping through the decomposition and
linking stages, not of advising accuracy. It is a useful component test with real diagnostic
value — [§6.2](#62-rmit) shows it separating the two engines sharply — but it cannot support a
claim about deployed verification quality. The registry records this as
`component_only_not_advising_completeness`.

### 3.4 RMIT completeness benchmark and the graph-destruction control

`scripts/generate_advising_benchmark.py` builds 181 set-valued responses over the 50 courses,
under five conditions: `complete_correct`, `complete_plus_distractor`, `omit_one`,
`corrupted_member`, `omit_multiple`. Splits are assigned by `sha256(subject_id) % 10`
(development 0–5, calibration 6–7, test 8–9), grouping **by course**, so no course appears in two
splits. The test split holds 33 responses.

The same circularity applies, and here it is explicit in code: line 90 of the generator calls
`AnswerCompletenessVerifier.verify()` to mint the `gold_completeness` label that the control later
predicts with that same verifier. A 100% baseline is therefore structurally guaranteed and carries
no information. Only the *destruction delta* is informative.

---

## 4. Experimental Methodology

### 4.1 Design

A 2 (engine) × 3 (dataset) factorial, one run per cell, plus one deterministic control. All cells
used `--max_workers 1`; RMIT used `--seed 42`. Jobs ran as parallel PowerShell background jobs
with per-job logs and a process manifest recording exit codes and UTC timestamps.

Every cell was run twice: once before the [§5](#5-defect-analysis) repair and once after, on
identical inputs and settings. This was not planned as a replication design, but it yields one
([§7](#7-run-to-run-reliability)).

### 4.2 Metrics

Recomputed from row-level predictions by `scripts/summarize_rerun_results.py`; recomputed and
harness-stored values agree in all twelve runs.

* **Accuracy** — exact verdict match. Non-decision outcomes (`Out-of-scope`, `Error`) can never
  match a gold label and so count as errors.
* **95% CI** — IID bootstrap over rows, 1,000 resamples.
* **Macro-F1** — mean F1 over classes with non-zero support.
* **Majority floor** — accuracy of always predicting the most frequent gold label.
* **Coverage** — share of rows on which the pipeline returned an actual decision. On FactKG,
  forced-binary scoring means only `Supported`/`Contradicted` count.
* **Selective accuracy** — accuracy restricted to covered rows.

**A scoring asymmetry worth stating.** `Out-of-scope` counts against accuracy but is invisible to
per-class precision, since it is not a label class. A pipeline that abstains never incurs a false
positive. This is why `azure-4.1-mini` on RMIT posts macro-F1 (0.988) *above* its accuracy
(0.973): its seven `Out-of-scope` outputs suppress recall without ever costing precision. Macro-F1
and accuracy are not comparable across systems with different abstention rates.

### 4.3 Why no clustered confidence intervals

The saved rows carry no subject-entity field. The only available grouping key is the id prefix,
which encodes the *gold label* (`codex-supported-…`, `rmit-one-hop-supported-…`), so resampling it
would produce an interval with no valid interpretation. `summarize_rerun_results.py` therefore
declines to emit one. Where rows share a subject entity, the true intervals are **wider** than
those reported in [§6](#6-results). The graph-destruction control in
[§6.4](#64-graph-destruction-control) does cluster properly, because its rows carry `subject_id`.

---

## 5. Defect Analysis

### 5.1 The defect

`stage_3_map_claim_to_triple` defines a local helper at line 268:

```python
def mapped(subject_code, mapped_relation, object_value, entity_score):
```

and rebound the same name to a boolean flag at line 305, inside the unclassified-relation
fallback:

```python
if actual_relations:
    mapped = False          # shadows the helper
```

Every subsequent `return mapped(...)` — eleven call sites, lines 345–382 — then invoked a `bool`:

```
TypeError: 'bool' object is not callable
  File "verification_pipeline.py", line 382, in stage_3_map_claim_to_triple
```

We reproduced this deterministically with a stub LLM and no network access, confirming an
implementation defect rather than a provider fault.

### 5.2 Reachability

The branch requires the relation to be `unclassified`, the subject to resolve, and the record to
carry at least one non-reserved relation key. On FactKG all three hold routinely:
`verify_with_context` writes arbitrary FactKG relation names as keys of a synthetic course record,
and the FactKG prompt instructs the model to emit `unclassified` for any claim outside the
supplied relation list.

Because *every* exit path from the branch calls `mapped(...)`, any execution with a non-empty
`actual_relations` must crash. Zero crashes were observed on RMIT and CoDEx pre-fix, which proves
the branch never executed there — and therefore that **the repair cannot have changed RMIT or
CoDEx behaviour.** This is what licenses the variance analysis in [§7](#7-run-to-run-reliability).

### 5.3 How the harness converted crashes into accuracy

`eval_harness.py:277-288` catches the exception and substitutes a default label — `Contradicted`
on FactKG. That label is also FactKG's majority class (64.6%):

| Engine | Rows crashed | Crashes scored **correct** |
| --- | ---: | ---: |
| `azure-4.1-mini` | 113 / 500 (22.6%) | 111 |
| `gemma-4-e4b` | 30 / 500 (6.0%) | 22 |

Crashes concentrated in the `existence` slice (100 of 113 for `azure-4.1-mini`) — precisely where
claims fail to match a relation class.

Before the repair, the defensible bound on true accuracy was wide: between 59.2% (every crash
counted wrong) and 81.4% (as scored), a 22-point band.

### 5.4 Repair and measured effect

We renamed the boolean to `relation_was_mapped`, leaving the helper intact, and added
`StageThreeFallbackTests` covering the fallback path (suite: 23 → 25 tests, all passing). The
post-fix runs show **zero crashes across all six cells**, and no previously-masked exception
surfaced.

| Cell | Pre-fix accuracy | Post-fix accuracy | Δ | Crashes removed |
| --- | ---: | ---: | ---: | ---: |
| FactKG / `azure-4.1-mini` | 81.40% | **80.20%** | −1.20 | 113 |
| FactKG / `gemma-4-e4b` | 80.00% | **79.80%** | −0.20 | 30 |

The 113 recovered rows resolved overwhelmingly to `Out-of-scope` (raw `Out-of-scope` rose 48→139),
which forced-binary scoring maps to `Contradicted` — the same label the crash handler had been
substituting.

> [!WARNING]
> **The small delta is a coincidence, not exoneration.** The harness's default label happened to
> coincide with what the repaired code mostly produces on this dataset. Had the default been
> `Supported`, or had the majority class been reversed, the same defect would have moved the
> headline by roughly twenty points. The measured 1.2-point delta is a property of this
> dataset's label prior, and provides no assurance for any other dataset or default. The
> instrumentation flaw — silently converting an exception into a scored prediction — is
> independent of the defect and remains present.

---

## 6. Results

All figures below are post-fix (`rerun_20260725_fixed`), recomputed from row-level predictions.

### 6.1 Headline

| Dataset | Engine | n | Accuracy | 95% CI (IID) | Majority floor | Macro-F1 | Coverage | Selective acc. |
| --- | --- | ---: | ---: | :---: | ---: | ---: | ---: | ---: |
| RMIT | `azure-4.1-mini` | 300 | **97.33%** | [95.33%, 99.00%] | 41.67% | 0.988 | 97.67% | 99.66% |
| RMIT | `gemma-4-e4b` | 300 | **92.33%** | [89.33%, 95.33%] | 41.67% | 0.921 | 97.67% | 94.54% |
| FactKG | `azure-4.1-mini` | 500 | **80.20%** | [76.80%, 83.40%] | 64.60% | 0.777 | 56.60% | 74.56% |
| FactKG | `gemma-4-e4b` | 500 | **79.80%** | [76.20%, 83.20%] | 64.60% | 0.752 | 40.00% | 85.50% |
| CoDEx | `azure-4.1-mini` | 500 | **41.80%** | [37.40%, 46.00%] | 35.80% | 0.345 | 99.60% | 41.77% |
| CoDEx | `gemma-4-e4b` | 500 | **37.20%** | [32.60%, 41.60%] | 35.80% | 0.285 | 89.60% | 37.05% |

Relative to the majority floor: RMIT clears it by 51–56 points, FactKG by 15 points, CoDEx by 1.4
and 6.0 points. The `gemma-4-e4b` CoDEx interval [32.60%, 41.60%] **contains the 35.80% floor**,
so that cell is not distinguishable from always predicting `Not-in-KG`.

### 6.2 RMIT

| Reasoning type | n | `azure-4.1-mini` | `gemma-4-e4b` |
| --- | ---: | ---: | ---: |
| one-hop (incl. 50 `Not-in-KG`) | 100 | 100.0% | 99.0% |
| conjunction | 50 | 100.0% | 100.0% |
| negation | 50 | 100.0% | 100.0% |
| existence | 50 | 98.0% | **58.0%** |
| multi-hop | 50 | **86.0%** | 98.0% |

The engines fail on **disjoint** slices, and their full error compositions are small enough to
state exhaustively:

| Engine | Total errors | Composition |
| --- | ---: | --- |
| `azure-4.1-mini` | 8 / 300 | multi-hop: 4 `Contradicted`→`Out-of-scope`, 3 `Supported`→`Out-of-scope`; existence: 1 `Supported`→`Contradicted` |
| `gemma-4-e4b` | 23 / 300 | existence: 16 `Supported`→`Not-in-KG`, 4 `Supported`→`Out-of-scope`, 1 `Contradicted`→`Out-of-scope`; multi-hop: 1; one-hop: 1 |

`azure-4.1-mini` makes exactly **one** substantively wrong verdict in 300 rows; its remaining
seven failures are all `Out-of-scope` — the pipeline declining to parse rather than answering
incorrectly, concentrated entirely in the multi-hop slice. `gemma-4-e4b`'s 21 existence failures
are likewise non-assertive: 20 of them abstain (`Not-in-KG` or `Out-of-scope`) rather than assert
a falsehood.

Since both engines query the same graph, and nearly every failure is an abstention rather than a
wrong verdict, these are decomposition and linking failures, not retrieval failures. The existence
generator produces the pipeline's hardest input — a coordinator-name-and-email claim carrying no
course code — and `gemma-4-e4b` frequently cannot map it to `taughtBy`.

Per-class, post-fix:

| Class | `azure-4.1-mini` P / R | `gemma-4-e4b` P / R |
| --- | :---: | :---: |
| Supported | 1.000 / 0.968 | 1.000 / 0.824 |
| Contradicted | 0.992 / 0.968 | 1.000 / 0.992 |
| Not-in-KG | 1.000 / 1.000 | 0.758 / 1.000 |

`gemma-4-e4b`'s `Not-in-KG` precision of 0.758 is the mirror image of its existence failure: it
over-assigns that class, absorbing 16 rows that should have been `Supported`.

**Interpretation is bounded by [§3.3](#33-rmit-claim-set-construction--and-its-circularity).**
These are template round-trip rates. The engine separation is a real and useful signal about
decomposition robustness; the absolute values are not advising accuracy.

### 6.3 CoDEx

Both engines sit near the floor, and the per-class view shows why: **the pipeline has effectively
lost the `Supported` class.**

| Class | Support | `azure-4.1-mini` P / R / F1 | `gemma-4-e4b` P / R / F1 |
| --- | ---: | :---: | :---: |
| Supported | 155 | 1.000 / **0.039** / 0.075 | 1.000 / **0.006** / 0.013 |
| Contradicted | 166 | 0.378 / 0.753 / 0.503 | 0.371 / 0.337 / 0.353 |
| Not-in-KG | 179 | 0.479 / 0.436 / 0.456 | 0.371 / 0.721 / 0.490 |

`azure-4.1-mini` returns `Supported` 6 times in 500; `gemma-4-e4b` once. Precision is 1.000 in
both cases — when the pipeline does commit, it is right — so this is **pure recall failure**, not
a threshold that can be tuned.

The misdirected mass reveals opposite failure modes:

| True class → predicted | `azure-4.1-mini` | `gemma-4-e4b` |
| --- | ---: | ---: |
| Supported → Contradicted | **105** / 155 (67.7%) | 45 / 155 (29.0%) |
| Supported → Not-in-KG | 44 / 155 (28.4%) | **109** / 155 (70.3%) |

`azure-4.1-mini` asserts falsehood about two-thirds of genuinely supported claims — a
false-contradiction rate of 67.7%, the most serious error mode for a verifier, since a confident
wrong contradiction is worse than an abstention. `gemma-4-e4b` instead abstains on 70.3% of them.
Their headline accuracies differ by 4.6 points and conceal entirely different behaviour.

Mechanically this is consistent with entity/relation linking failing against the 1,182-entity
CoDEx graph: unresolved subjects route to `Not-in-KG`, while resolved subjects with unmatched
objects route to `Contradicted` under closed-world dispatch. Precision of 1.000 on the few
`Supported` outputs indicates the verification logic is sound where linking succeeds.

CoDEx additionally carries the registry finding `invalidated_heldout_edges_present`: records
marked held out do not have the true edge removed from the verification graph. These numbers
should not be read as a clean measurement of the tri-state protocol.

### 6.4 Graph-destruction control

Deterministic, no LLM. Paired over the 33 held-out test responses; 231 row-level predictions.
Intervals are subject-clustered bootstraps of the *paired drop*, 1,000 resamples.

| Condition | Accuracy | Observed drop | Clustered 95% CI for drop |
| --- | ---: | ---: | :---: |
| Baseline | 100.0% | — | — |
| Empty graph | 48.5% | 51.5% | [42.9%, 56.8%] |
| Shuffled, seed 11 | 57.6% | 42.4% | [34.5%, 48.5%] |
| Shuffled, seed 23 | 57.6% | 42.4% | [34.5%, 47.1%] |
| Shuffled, seed 37 | 57.6% | 42.4% | [34.5%, 47.1%] |
| Shuffled, seed 53 | 57.6% | 42.4% | [34.5%, 48.5%] |
| Shuffled, seed 71 | 57.6% | 42.4% | [35.7%, 48.5%] |

Shuffling uses zero-fixed-point within-relation derangements, preserving the object multiset,
relation density, and type distribution while destroying factual content. All five seeds agree to
within 0.1 points and every interval excludes zero.

**This control answers RQ1 affirmatively for the deterministic completeness component**: its
outputs depend on graph content, not surface form. It ran bit-identically pre- and post-fix
(matching graph, benchmark, and script hashes), confirming determinism.

Its 100% baseline is structurally guaranteed ([§3.4](#34-rmit-completeness-benchmark-and-the-graph-destruction-control))
and carries no information. Only the delta does. It is also a component check on a deterministic
set-comparison routine, not on the LLM pipeline evaluated in §6.1–6.3.

### 6.5 FactKG

| Class | `azure-4.1-mini` P / R / F1 | `gemma-4-e4b` P / R / F1 |
| --- | :---: | :---: |
| Supported | 0.750 / 0.661 / 0.703 | 0.852 / 0.520 / 0.646 |
| Contradicted | 0.826 / 0.879 / 0.852 | 0.783 / 0.950 / 0.859 |
| Not-in-KG | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 |

| Reasoning type | n | `azure-4.1-mini` | `gemma-4-e4b` |
| --- | ---: | ---: | ---: |
| existence | 375 | 78.7% | 74.7% |
| num1\|substitution | 125 | 84.8% | **95.2%** |

Two structural observations, both independent of the defect:

**`Not-in-KG` is unreachable by construction.** `eval_harness.py:249-253` collapses `Not-in-KG`,
`Out-of-scope`, and `Abstained` into `Contradicted`. The class has support 0 and F1 0.000 in every
FactKG run, and every abstention is scored as an assertion of falsehood. This answers **RQ3
negatively**: a forced-binary benchmark cannot evaluate an abstention-capable verifier, because
the protocol destroys the distinction before scoring. This is a property of the benchmark, not of
the engines.

**Coverage and selective accuracy trade off inversely.** `azure-4.1-mini` covers 56.6% at 74.56%
selective accuracy; `gemma-4-e4b` covers 40.0% at 85.50%. The more conservative engine is
substantially more accurate where it commits — the expected selective-prediction signature — but
because abstention is scored as `Contradicted`, that discipline is invisible in the 0.4-point
headline gap between them.

---

## 7. Run-to-Run Reliability

The unplanned paired rerun permits a direct measurement of nondeterminism. In the four cells where
the repair is provably unreachable ([§5.2](#52-reachability)), any difference is attributable to
LLM sampling alone.

| Cell | Pre-fix acc. | Post-fix acc. | Δ accuracy | Prediction flips | Flip rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| RMIT / `azure-4.1-mini` | 98.00% | 97.33% | −0.67 | 6 / 300 | 2.00% |
| RMIT / `gemma-4-e4b` | 92.00% | 92.33% | +0.33 | 15 / 300 | 5.00% |
| CoDEx / `azure-4.1-mini` | 42.40% | 41.80% | −0.60 | 48 / 500 | **9.60%** |
| CoDEx / `gemma-4-e4b` | 39.20% | 37.20% | −2.00 | 32 / 500 | 6.40% |

Mean |Δ accuracy| 0.90 points (max 2.00); mean flip rate 5.75% (max 9.60%).

Two consequences:

1. **Aggregate stability badly understates instability.** CoDEx / `azure-4.1-mini` moved 0.6
   points in accuracy while 9.6% of its individual predictions changed — offsetting flips cancel.
   Reporting only accuracy hides this; any claim about *which rows* the system gets right needs
   replication.
2. **Between-engine gaps below ~2 points are not resolvable from single runs.** The 4.6-point
   CoDEx gap and the 5.0-point RMIT gap survive this floor; the 0.4-point FactKG gap does not, and
   we decline to interpret it.

`eval_rmit.py` sets `random.seed(42)`, but this seeds only Python's `random` module — it does not
constrain LLM sampling, and decomposition runs at temperature 0.1/0.2. The runs are not
reproducible in the bitwise sense; the `--seed` flag creates a misleading impression of
determinism. Only the graph-destruction control is genuinely deterministic.

---

## 8. Threats to Validity

### 8.1 Construct validity

* **RMIT circularity** ([§3.3](#33-rmit-claim-set-construction--and-its-circularity)). Evaluated
  strings are templates interpolated from the fields the verifier queries; the paraphrase is
  never evaluated. Measures round-tripping, not advising quality.
* **Control circularity** ([§3.4](#34-rmit-completeness-benchmark-and-the-graph-destruction-control)).
  Gold labels are minted by the verifier under test. Only the destruction delta is informative.
* **FactKG label collapse** ([§6.5](#65-factkg)). Abstention is scored as falsehood, so the
  benchmark cannot measure the system's distinguishing capability.
* **Occupancy is not completeness** ([§2.1](#21-pipeline-stages)). CWA/OWA routing keys on how
  often a field is populated locally, which says nothing about world coverage. On a sparse graph a
  relation can look "closed" merely because the few records present all have the field.

### 8.2 Internal validity

* **Instrumentation converts failures into scores** ([§5.3](#53-how-the-harness-converted-crashes-into-accuracy)).
  Unfixed. The defect is repaired; the harness behaviour that hid it is not.
* **Confounded self-consistency** ([§2.2](#22-two-behaviours-that-materially-affect-measurement)).
  `decomposition_agreement` is a hardcoded 1.0 on FactKG and a measured value elsewhere.
* **Uncalibrated confidence** ([§2.2](#22-two-behaviours-that-materially-affect-measurement)).
  Coverage and selective accuracy are descriptive only.
* **Nondeterminism** ([§7](#7-run-to-run-reliability)). Single run per cell; 5.75% mean flip rate.

### 8.3 External validity

* **Prefix sampling, not random** ([§3.1](#31-overview)). The first 500 rows of FactKG and CoDEx
  need not be representative of 9,041 and 1,000.
* **CoDEx held-out edges present.** Registry finding `invalidated_heldout_edges_present`.
* **Two engines, one institution, one advising intent** (`all_prerequisites`). No prerequisite
  Boolean structure (`AND`/`OR`/alternatives) is modelled.
* **Single reviewer.** The expert audit design supports source correction but not
  inter-annotator agreement; it remains `awaiting_review` for 20 calibration/test courses.

### 8.4 Statistical conclusion validity

* **Intervals are anti-conservative** ([§4.3](#43-why-no-clustered-confidence-intervals)). IID row
  bootstraps ignore subject clustering; true intervals are wider.
* **No multiplicity correction.** Six cells and multiple per-class comparisons are reported
  without family-wise adjustment. Treat individual comparisons as exploratory.
* **No paired significance test between engines.** Differences are described, not tested.

---

## 9. What May and May Not Be Claimed

**Supported by these artifacts.**

1. The stage-3 defect existed, is reproducible, is repaired, and inflated a benchmark cell by
   converting 113 crashes into 111 scored-correct predictions ([§5](#5-defect-analysis)).
2. The deterministic completeness component is graph-sensitive: destroying factual content while
   preserving structure costs 42–52 points with intervals excluding zero
   ([§6.4](#64-graph-destruction-control)).
3. On CoDEx the pipeline reaches `Supported` for 0.6–3.9% of genuinely supported claims, at
   precision 1.000 ([§6.3](#63-codex)).
4. Paired reruns under identical settings flip 2.0–9.6% of predictions
   ([§7](#7-run-to-run-reliability)).
5. FactKG's forced-binary protocol cannot measure abstention ([§6.5](#65-factkg)).

**Not supported.**

1. That the system performs advising-quality verification. RMIT is circular
   ([§3.3](#33-rmit-claim-set-construction--and-its-circularity)).
2. That the LLM pipeline (as opposed to the deterministic component) is graph-grounded. No
   destruction control was run against the LLM pipeline in this study.
3. Any ranking of the two engines on FactKG (0.4 points, below the noise floor).
4. Any calibration, risk-control, or deployment claim. Confidence is uncalibrated by design and no
   calibration split was used.
5. That the 1.2-point post-fix delta shows the defect was harmless
   ([§5.4](#54-repair-and-measured-effect)).

---

## 10. Conclusions and Future Work

Answering the research questions as the evidence permits:

* **RQ1 (Grounding).** Affirmative for the deterministic completeness component. **Unanswered for
  the LLM pipeline** — the required destruction control was never run against it.
* **RQ2 (Transfer).** Negative. RMIT 97.3% versus CoDEx 41.8% is a collapse, though the RMIT side
  is inflated by circularity, so the true gap is unmeasured. The CoDEx per-class analysis locates
  the failure in linking-driven recall, not verification logic.
* **RQ3 (Abstention).** The pipeline abstains substantially (coverage 40–57% on FactKG, with the
  expected inverse coverage/accuracy relationship). Existing binary benchmarks cannot score this.
* **RQ4 (Measurement validity).** Negative, and this is the study's principal result. One harness
  converted exceptions into majority-class predictions; another disables self-consistency by a
  silent size threshold; a third mints gold labels with the system under test. Each was found by
  reading source alongside outputs, not by inspecting aggregates.

**Prioritised next steps.**

1. Make crashes non-scoring in `eval_harness.py` — record an explicit outcome rather than
   substituting a class label. This is the highest-value fix and is independent of any model.
2. Run a graph-destruction control against the **LLM pipeline** on RMIT and CoDEx. Without it, RQ1
   is open for the system actually being reported.
3. Diagnose CoDEx `Supported` recall, beginning with entity linking against `data/codex_graph.json`
   given precision 1.000.
4. Replicate each cell ≥3 times and report dispersion; the 5.75% flip rate makes single runs
   inadequate.
5. Re-emit rows with subject-entity ids so clustered intervals become computable.
6. De-circularize RMIT: verify `text` rather than `raw_claim`, or build an independently authored
   response set. Complete the advisor audit for the 20 outstanding calibration/test courses.
7. Rebuild CoDEx tri-state views with held-out edges genuinely removed.
8. Remove or document the `--seed` flag in `eval_rmit.py`, which does not make runs reproducible.

---

## 11. Reproduction

Environment: Python 3.13.5, `.venv` at repository root. Regression suite: 25 tests.

```powershell
Set-Location C:\Users\Admin\Desktop\crawler
& .venv\Scripts\python.exe -m unittest discover -s tests
```

Recompute every aggregate in this paper from saved row-level predictions:

```powershell
& .venv\Scripts\python.exe scripts\summarize_rerun_results.py `
    --dir output\experiments\rerun_20260725_fixed `
    --out output\experiments\rerun_20260725_fixed\aggregate_summary.json
```

Reproduce the paired pre/post comparison in [§5.4](#54-repair-and-measured-effect) and
[§7](#7-run-to-run-reliability):

```powershell
& .venv\Scripts\python.exe scripts\compare_runs.py `
    --before output\experiments\rerun_20260725 `
    --after output\experiments\rerun_20260725_fixed
```

Reproduce the deterministic control ([§6.4](#64-graph-destruction-control)):

```powershell
& .venv\Scripts\python.exe scripts\run_graph_destruction_control.py `
    --rows output\experiments\rerun_20260725_fixed\rmit_graph_control.rows.jsonl `
    --summary output\experiments\rerun_20260725_fixed\rmit_graph_control.summary.json
```

Confirm zero stage-3 crashes post-fix:

```powershell
Get-ChildItem output\experiments\rerun_20260725_fixed\*.log |
    ForEach-Object { "{0}: {1}" -f $_.Name,
        (Select-String -Path $_.FullName -Pattern "'bool' object is not callable").Count }
```

### Artifact inventory

| Artifact | Path |
| --- | --- |
| Post-fix row-level predictions | `output/experiments/rerun_20260725_fixed/*.json` |
| Post-fix per-job logs | `output/experiments/rerun_20260725_fixed/*.log` |
| Process manifest (exit codes, UTC timestamps) | `output/experiments/rerun_20260725_fixed/process_manifest.json` |
| Recomputed aggregates | `output/experiments/rerun_20260725_fixed/aggregate_summary.json` |
| Control rows / summary | `output/experiments/rerun_20260725_fixed/rmit_graph_control.*` |
| Pre-fix artifacts (defect case study) | `output/experiments/rerun_20260725/` |
| Registry status | `experiments/registry.json` |

`output/` is git-ignored; artifacts are local to the run machine.
