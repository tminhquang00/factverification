# Comprehensive Report — KG Fact-Verification Pipeline

**Subject study:** `rerun_20260725_fixed` (2026-07-25)
**Engines:** `azure-4.1-mini` (Azure OpenAI), `google/gemma-4-e4b` (LM Studio, local)
**Prepared:** 2026-07-25
**Basis:** independent recomputation from row-level artifacts, plus four new diagnostic experiments
**Status of the study reviewed:** `candidate` (per `experiments/registry.json`) — this report does not promote it

---

## 0. Scope and verification statement

This report reviews the current result set, then documents data, methodology, results, analysis,
contributions, and limitations. Every headline figure was **recomputed from the saved row-level
predictions**, not copied from the existing write-up.

What was checked, and the outcome:

| Check | Method | Outcome |
| --- | --- | --- |
| All six cell accuracies, macro-F1, coverage, selective accuracy, majority floors | Independent script over `results_detail` rows | **All match** the values in `rerun_20260725_paper.md` |
| Per-class precision/recall, confusion matrices, per-reasoning-type slices | Independent recount | **All match** |
| Pre-fix crash counts and their scoring | `raw_pred == "Error"` count + log grep (UTF-16) | **Confirmed**: 113 / 30 crashes, 111 / 22 scored correct |
| Post-fix crash count | Log grep across all seven post-fix logs | **Confirmed zero** |
| Run-to-run flip rates | `scripts/compare_runs.py` re-executed | **Confirmed**: 2.00 / 5.00 / 9.60 / 6.40%, mean 5.75% |
| Graph-destruction control | Summary artifact + hashes | **Confirmed**: 100% → 48.5% / 57.6%, five seeds agree |
| Regression suite | `python -m unittest discover -s tests` | **25 tests, all passing** |
| Source-level claims (`verification_pipeline.py:230`, `:268/:306`, `eval_harness.py:277-288`, `eval_rmit.py:54`) | Direct read | **All confirmed as described** |

**The existing paper's reported numbers are accurate and its reasoning about the defect is sound.**
The corrections in [§7](#7-corrections-to-the-existing-write-up) concern *causal attribution* and
*sampling representativeness*, not arithmetic.

Four new experiments were run for this report ([§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure)–[§5.4](#54-new-finding-c-the-factkg-subsample-is-severely-unrepresentative)); they change two of the study's
principal conclusions.

---

## 1. System under evaluation

A post-hoc claim-level verifier. Input: a natural-language statement plus a knowledge graph.
Output: one of three verdicts — `Supported`, `Contradicted`, `Not-in-KG` — plus two non-decision
outcomes, `Out-of-scope` (unparseable or off-ontology) and `Error` (exception, harness-level).

| Stage | Function | Mechanism |
| --- | --- | --- |
| 2. Decomposition | statement → atomic claims | LLM, schema-guided; two passes at T=0.1 / 0.2, intersection kept |
| 3. Mapping | claim → `(subject, relation, object)` | exact/normalized index lookup, then `all-MiniLM-L6-v2` bi-encoder cosine retrieval; TF-IDF char n-gram fallback |
| 4. Verification | triple → verdict | relation-dispatched `KGStore` lookup under CWA/OWA routing |
| — | Confidence | `base_conf × entity_score × decomposition_agreement`, **uncalibrated** |

**Routing.** `get_world_assumption` (`verification_pipeline.py:385`) uses per-relation *occupancy* —
the fraction of entity records with that field populated (`KGStore.estimate_relation_occupancy`).
Occupancy ≥ `cwa_threshold` (0.85) → closed-world (absence ⇒ `Contradicted`); else open-world
(absence ⇒ `Not-in-KG`). All runs used `dynamic`. The codebase correctly notes this is *occupancy*,
not completeness: it says nothing about world coverage.

**Two behaviours that distort measurement, both confirmed in source:**

* `verification_pipeline.py:230` returns after a single decomposition pass when the graph holds
  fewer than 50 entities, hardcoding `decomposition_agreement = 1.0`. FactKG builds a *transient
  per-claim* context, always far below 50, so **every FactKG run silently skips self-consistency**.
  RMIT (exactly 50, strict `<`) and CoDEx (1,182) do run both passes. Cross-dataset confidence
  comparison is confounded.
* Confidence is a heuristic product with no fitted mapping to correctness. Coverage and selective
  accuracy are descriptive statistics at the default operating point, **not risk guarantees**.

A `DualRiskController` (`abstention_controller.py`) with independent wrong-answer and omission
budgets exists and correctly defers whenever risks are uncalibrated — which, today, is always. It
is not exercised by any cell in this study.

---

## 2. Data

### 2.1 Inventory

| Dataset | File | Total rows | Used | Graph | Graph size |
| --- | --- | ---: | ---: | --- | ---: |
| RMIT claim set | `data/rmit_test_set.jsonl` | 300 | 300 | `data/rmit_graph.json` | 50 courses |
| FactKG | `data/factkg_test.jsonl` | 9,041 | first 500 | per-claim transient context | varies |
| CoDEx | `data/codex_test.jsonl` | 1,000 | first 500 | `data/codex_graph.json` | 1,182 entities |
| RMIT completeness | `data/advising/rmit_prerequisite_completeness_v0.jsonl` | 181 | 33 (test split) | `data/rmit_graph.json` | 50 courses |

Sampling is by prefix (`data[:limit]`). No seed governs which rows enter the sample.
[§5.4](#54-new-finding-c-the-factkg-subsample-is-severely-unrepresentative) shows this is benign
for CoDEx and severe for FactKG.

### 2.2 Label distributions (evaluated subsets)

| Dataset | Supported | Contradicted | Not-in-KG | Majority floor |
| --- | ---: | ---: | ---: | ---: |
| RMIT (n=300) | 125 | 125 | 50 | 41.67% |
| FactKG (n=500) | 177 | 323 | — | 64.60% |
| CoDEx (n=500) | 155 | 166 | 179 | 35.80% |

CoDEx's near-balanced three-class split makes its 35.80% floor the most demanding.

### 2.3 RMIT claim set — construction and circularity

`generate_dataset.py` emits six generators × 50 rows: one-hop (credit value), conjunction
(prerequisite + school), existence (coordinator + email), multi-hop (two-step prerequisite chain),
negation, and 50 `Not-in-KG` rows with randomly generated six-digit course codes. The `Not-in-KG`
rows carry `reasoning_type = "one-hop"`, hence n=100 in that slice.

Each record holds two text fields: `raw_claim`, a template interpolated from KG fields
(`"Course 038974 (Programming A) is worth 12 credit points."`), and `text`, an LLM paraphrase at
T=0.7.

> **Confirmed at `eval_rmit.py:54`: the pipeline is handed `raw_claim`. The paraphrase `text` is
> generated, stored, and never verified.** The verifier therefore reads a machine-built sentence
> whose object value was interpolated from the very field it then looks up. Negatives come from
> deterministic perturbation (`24 if credits == 12 else 12`; school flipped; a hardcoded wrong id).

RMIT measures **template round-tripping through decomposition and linking**, not advising accuracy.
Registry status: `component_only_not_advising_completeness`.

### 2.4 RMIT completeness benchmark and its control

`scripts/generate_advising_benchmark.py` builds 181 set-valued responses over 50 courses under five
conditions (`complete_correct`, `complete_plus_distractor`, `omit_one`, `corrupted_member`,
`omit_multiple`). Splits are assigned by `sha256(subject_id) % 10` and grouped **by course**, so no
course spans splits: development 106, calibration 42, test 33. Gold completeness: 100 complete /
81 incomplete.

The generator mints `gold_completeness` by calling `AnswerCompletenessVerifier.verify()` — the same
routine the control later evaluates. **A 100% baseline is structurally guaranteed and carries zero
information.** Only the destruction delta is interpretable.

---

## 3. Methodology

**Design.** 2 (engine) × 3 (dataset) factorial, one run per cell, plus one deterministic control.
All cells `--max_workers 1`; RMIT `--seed 42`. Jobs ran as parallel PowerShell background jobs with
per-job logs and a manifest recording exit codes and UTC timestamps (all six exit code 0, verified).

Every cell ran twice — once before and once after the stage-3 repair, on identical inputs. Not
planned as a replication, but it yields one ([§4.4](#44-run-to-run-reliability)).

**Metrics**, recomputed by `scripts/summarize_rerun_results.py` and independently reproduced here:

* **Accuracy** — exact verdict match. `Out-of-scope` and `Error` can never match, so they count as
  errors.
* **95% CI** — IID bootstrap over rows, 1,000 resamples.
* **Macro-F1** — mean F1 over classes with non-zero support.
* **Majority floor** — always predicting the most frequent gold label.
* **Coverage** — share of rows returning an actual decision. On FactKG, forced-binary scoring means
  only `Supported`/`Contradicted` count (verified: 283/500 and 200/500).
* **Selective accuracy** — accuracy restricted to covered rows.

**A scoring asymmetry.** `Out-of-scope` counts against accuracy but is invisible to per-class
precision, so abstention never incurs a false positive. This is why `azure-4.1-mini` on RMIT posts
macro-F1 0.988 *above* accuracy 0.973. **Macro-F1 and accuracy are not comparable across systems
with different abstention rates.**

**No clustered intervals.** Saved rows carry no subject-entity field, and the only grouping key
(the id prefix) encodes the gold label, so clustering on it would be meaningless. Reported
intervals are therefore **anti-conservative**. The graph-destruction control does cluster properly
(rows carry `subject_id`).

---

## 4. Results

All figures post-fix, independently recomputed.

### 4.1 Headline

| Dataset | Engine | n | Accuracy | 95% CI (IID) | Majority floor | Macro-F1 | Coverage | Selective acc. |
| --- | --- | ---: | ---: | :---: | ---: | ---: | ---: | ---: |
| RMIT | `azure-4.1-mini` | 300 | **97.33%** | [95.33, 99.00] | 41.67% | 0.988 | 97.67% | 99.66% |
| RMIT | `gemma-4-e4b` | 300 | **92.33%** | [89.33, 95.33] | 41.67% | 0.921 | 97.67% | 94.54% |
| FactKG | `azure-4.1-mini` | 500 | **80.20%** | [76.80, 83.40] | 64.60% | 0.777 | 56.60% | 74.56% |
| FactKG | `gemma-4-e4b` | 500 | **79.80%** | [76.20, 83.20] | 64.60% | 0.752 | 40.00% | 85.50% |
| CoDEx | `azure-4.1-mini` | 500 | **41.80%** | [37.40, 46.00] | 35.80% | 0.345 | 99.60% | 41.77% |
| CoDEx | `gemma-4-e4b` | 500 | **37.20%** | [32.60, 41.60] | 35.80% | 0.285 | 89.60% | 37.05% |

Margins over floor: RMIT 51–56 points, FactKG 15 points (but see
[§5.4](#54-new-finding-c-the-factkg-subsample-is-severely-unrepresentative)), CoDEx 6.0 and 1.4
points. **The `gemma-4-e4b` CoDEx interval contains the floor**, so that cell is not distinguishable
from always predicting `Not-in-KG`.

### 4.2 The stage-3 defect

`stage_3_map_claim_to_triple` defined a helper `mapped(...)` at line 268 and rebound the same name
to a boolean at line 305 inside the unclassified-relation fallback. Every later
`return mapped(...)` — eleven call sites — then invoked a `bool`:

```
TypeError: 'bool' object is not callable
```

Because *every* exit path from that branch calls `mapped(...)`, any execution with non-empty
`actual_relations` must crash. **Zero pre-fix crashes on RMIT and CoDEx therefore prove the branch
never executed there** — which is what licenses treating those four cells as a clean replication.

`eval_harness.py:277-288` catches the exception and substitutes the dataset default label —
`Contradicted` on FactKG, which is also FactKG's majority class:

| Engine | Rows crashed | Crashes scored **correct** | Concentrated in |
| --- | ---: | ---: | --- |
| `azure-4.1-mini` | 113 / 500 (22.6%) | 111 | `existence` (100 of 113) |
| `gemma-4-e4b` | 30 / 500 (6.0%) | 22 | `existence` (26 of 30) |

Pre-fix, the defensible bound on true accuracy spanned 59.2%–81.4%.

Repair: rename the boolean to `relation_was_mapped`; add `StageThreeFallbackTests` (suite 23 → 25).
Post-fix: **zero crashes in all six cells**, no previously-masked exception surfaced.

| Cell | Pre-fix | Post-fix | Δ | Crashes removed |
| --- | ---: | ---: | ---: | ---: |
| FactKG / `azure-4.1-mini` | 81.40% | **80.20%** | −1.20 | 113 |
| FactKG / `gemma-4-e4b` | 80.00% | **79.80%** | −0.20 | 30 |

> **The small delta is coincidence, not exoneration.** The recovered rows resolved overwhelmingly to
> `Out-of-scope` (raw count 48 → 139), which forced-binary scoring maps to `Contradicted` — the same
> label the crash handler substituted. Had the default been `Supported`, the same defect would have
> moved the headline by roughly twenty points. **The instrumentation flaw — silently converting an
> exception into a scored prediction — is independent of the defect and is still present.**

A third engine, `azure-5-mini`, was run pre-fix (140 FactKG crashes) and **dropped from the post-fix
sweep**. The post-fix study covers two of the three engines originally executed.

### 4.3 Per-dataset detail

**RMIT.** The engines fail on **disjoint** slices; error sets are small enough to state exhaustively.

| Reasoning type | n | `azure-4.1-mini` | `gemma-4-e4b` |
| --- | ---: | ---: | ---: |
| one-hop (incl. 50 `Not-in-KG`) | 100 | 100.0% | 99.0% |
| conjunction | 50 | 100.0% | 100.0% |
| negation | 50 | 100.0% | 100.0% |
| existence | 50 | 98.0% | **58.0%** |
| multi-hop | 50 | **86.0%** | 98.0% |

| Engine | Errors | Composition |
| --- | ---: | --- |
| `azure-4.1-mini` | 8 / 300 | multi-hop: 4 `Contradicted`→`Out-of-scope`, 3 `Supported`→`Out-of-scope`; existence: 1 `Supported`→`Contradicted` |
| `gemma-4-e4b` | 23 / 300 | existence: 16 `Supported`→`Not-in-KG`, 4 `Supported`→`Out-of-scope`, 1 `Contradicted`→`Out-of-scope`; multi-hop: 1; one-hop: 1 |

`azure-4.1-mini` makes exactly **one** substantively wrong verdict in 300 rows; the other seven are
`Out-of-scope` — declining to parse, all in multi-hop. 20 of `gemma-4-e4b`'s 21 existence failures
abstain rather than assert a falsehood. Since both engines query the same graph and nearly every
failure is an abstention, **these are decomposition and linking failures, not retrieval failures.**
The existence generator produces the hardest input — a coordinator-name-and-email claim carrying no
course code — and `gemma-4-e4b` frequently cannot map it to `taughtBy`. Its `Not-in-KG` precision
of 0.758 is the mirror image: it over-assigns that class, absorbing 16 rows that should be
`Supported`.

**CoDEx.** The pipeline has effectively lost one of its three classes.

| Class | Support | `azure-4.1-mini` P / R / F1 | `gemma-4-e4b` P / R / F1 |
| --- | ---: | :---: | :---: |
| Supported | 155 | 1.000 / **0.039** / 0.075 | 1.000 / **0.006** / 0.013 |
| Contradicted | 166 | 0.378 / 0.753 / 0.503 | 0.371 / 0.337 / 0.353 |
| Not-in-KG | 179 | 0.479 / 0.436 / 0.456 | 0.371 / 0.721 / 0.490 |

`azure-4.1-mini` returns `Supported` 6 times in 500; `gemma-4-e4b` once. The misdirected mass runs
in **opposite directions**:

| True → predicted | `azure-4.1-mini` | `gemma-4-e4b` |
| --- | ---: | ---: |
| Supported → Contradicted | **105** / 155 (67.7%) | 45 / 155 (29.0%) |
| Supported → Not-in-KG | 44 / 155 (28.4%) | **109** / 155 (70.3%) |

`azure-4.1-mini` asserts falsehood about two-thirds of genuinely supported claims — the most serious
error mode for a verifier. `gemma-4-e4b` abstains on 70.3% of them. Headline accuracies differ by
4.6 points and conceal entirely different behaviour. [§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure)
identifies the mechanism.

**FactKG.**

| Class | `azure-4.1-mini` P / R / F1 | `gemma-4-e4b` P / R / F1 |
| --- | :---: | :---: |
| Supported | 0.750 / 0.661 / 0.703 | 0.852 / 0.520 / 0.646 |
| Contradicted | 0.826 / 0.879 / 0.852 | 0.783 / 0.950 / 0.859 |
| Not-in-KG | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 |

`eval_harness.py:249-253` collapses `Not-in-KG`, `Out-of-scope`, and `Abstained` into
`Contradicted`. **`Not-in-KG` is unreachable by construction** — support 0, F1 0.000 in every FactKG
run — and every abstention is scored as an assertion of falsehood.

Coverage and selective accuracy trade off inversely as selective prediction predicts:
`azure-4.1-mini` covers 56.6% at 74.56%; `gemma-4-e4b` covers 40.0% at 85.50%. The more
conservative engine is far more accurate where it commits — but because abstention is scored as
`Contradicted`, that discipline is invisible in the 0.4-point headline gap.

**Graph-destruction control** (deterministic, no LLM; 33 test responses, 231 row-level predictions;
subject-clustered bootstrap of the paired drop, 1,000 resamples).

| Condition | Accuracy | Drop | Clustered 95% CI for drop |
| --- | ---: | ---: | :---: |
| Baseline | 100.0% | — | — |
| Empty graph | 48.5% | 51.5% | [42.9%, 56.8%] |
| Shuffled, seeds 11 / 23 / 37 / 53 / 71 | 57.6% | 42.4% | ≈[34.5%, 48.5%] |

Shuffling uses zero-fixed-point within-relation derangements, preserving object multiset, relation
density, and type distribution while destroying factual content. All five seeds agree to within 0.1
points; every interval excludes zero. The run reproduces **bit-identically** pre- and post-fix
(matching graph, benchmark, and script hashes).

This establishes graph-sensitivity **for the deterministic completeness component only**. Its 100%
baseline is structurally guaranteed and carries no information.

### 4.4 Run-to-run reliability

In the four cells where the repair is provably unreachable, any difference is LLM sampling alone.

| Cell | Pre-fix | Post-fix | Δ acc | Flips | Flip rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| RMIT / `azure-4.1-mini` | 98.00% | 97.33% | −0.67 | 6 / 300 | 2.00% |
| RMIT / `gemma-4-e4b` | 92.00% | 92.33% | +0.33 | 15 / 300 | 5.00% |
| CoDEx / `azure-4.1-mini` | 42.40% | 41.80% | −0.60 | 48 / 500 | **9.60%** |
| CoDEx / `gemma-4-e4b` | 39.20% | 37.20% | −2.00 | 32 / 500 | 6.40% |

Mean |Δ accuracy| 0.90 points (max 2.00); mean flip rate 5.75% (max 9.60%).

1. **Aggregate stability badly understates instability.** CoDEx / `azure-4.1-mini` moved 0.6 points
   while 9.6% of individual predictions changed — offsetting flips cancel.
2. **Between-engine gaps below ~2 points are not resolvable from single runs.** The 4.6-point CoDEx
   and 5.0-point RMIT gaps survive; the 0.4-point FactKG gap does not.

`eval_rmit.py` sets `random.seed(42)`, which seeds only Python's `random` module and does not
constrain LLM sampling (decomposition runs at T=0.1/0.2). **The `--seed` flag creates a misleading
impression of determinism.** Only the graph-destruction control is genuinely deterministic.

---

## 5. Analysis

### 5.1 What the aggregates hide

Three of this study's most consequential facts are invisible in the headline table: a 22.6% crash
rate scored as 81.4% accuracy; a class with 0.6–3.9% recall inside a 41.8% accuracy; and a 9.6%
prediction flip rate inside a 0.6-point accuracy move. Each was found by reading source alongside
row-level outputs. **Aggregate-level review would have caught none of them.**

### 5.2 New finding A — the CoDEx `Supported` collapse is an object-namespace bug, not a linking failure

The existing paper hypothesises that CoDEx failure is "consistent with entity/relation linking
failing against the 1,182-entity graph," and reads precision 1.000 as evidence that "the
verification logic is sound where linking succeeds." **Both are wrong.**

Feeding the *gold* `(subject, relation, object)` straight into stages 3–4 with **no LLM at all**:

* **Subject linking succeeds on 155 / 155 gold-`Supported` rows** — there is no subject-linking
  failure to diagnose.
* The pipeline still returns **`Contradicted` on 144 of 155**, `Supported` on 11.

The traces show why:

```
CLAIM  Sam Cooke -[genre]-> rhythm and blues
  stage-3 triple:  ('Q295919', 'genre', 'Q216288')
  graph value:     ['rhythm and blues', 'soul music', 'gospel music']
  verdict: Contradicted — "Value mismatch. Claimed Q216288, but actual is rhythm and blues, ..."
```

`data/codex_graph.json` keys entities by Wikidata Q-id but stores **object values as surface
labels**: of 17,203 object values, **17,203 are labels and 0 are Q-ids**. Stage 3 applies the same
`link_entity` routine to the object position, converting `"rhythm and blues"` → `Q216288`. Stage 4
then compares a Q-id against a label list and reports a value mismatch. The object is not *failing*
to link — it is linking *successfully into the wrong namespace*.

Verdict as a function of object namespace, over all 500 oracle-parsed rows:

| Object after stage 3 | Rows | → `Supported` | → `Contradicted` | → `Not-in-KG` |
| --- | ---: | ---: | ---: | ---: |
| resolved to a Q-id | 480 (96.0%) | **0** | 434 | 46 |
| left as a label | 20 (4.0%) | 16 | 4 | 0 |

**No row whose object resolved to a Q-id was ever verified `Supported`** — 96% of rows are excluded
from that class before the graph is consulted on the merits. This single defect explains all three
CoDEx observations:

1. **`Supported` recall 0.039 / 0.006** — the class is nearly unreachable.
2. **`Supported` precision 1.000 is an artifact**, not soundness. The survivors are exactly the rows
   where object linking happened to *fail* to find a Q-id.
3. **`Contradicted` recall 0.753 is largely spurious** — 163 of 166 gold-`Contradicted` rows are
   scored correct because the object mismatched for a *namespace* reason, not a factual one. The
   class is right for the wrong reason.

It also explains the engine split: `azure-4.1-mini` produces decompositions whose subjects resolve
more often (→ `Contradicted` via value mismatch), while `gemma-4-e4b` leaves more unresolved
(→ `Not-in-KG`). The 4.6-point accuracy gap reflects decomposition verbosity, not verification skill.

Note also that `world_assumption` is `None` on every one of these paths: the value-mismatch branch
fires **before** CWA/OWA dispatch. **CoDEx exercises essentially none of the project's headline C1
claim about per-relation world-assumption routing.**

### 5.3 New finding B — the LLM pipeline is not graph-grounded on CoDEx (RQ1, answered)

The existing paper lists RQ1 as "unanswered for the LLM pipeline — the required destruction control
was never run against it." That control can be run cheaply on the deterministic stage-3/4 path.
Applying the same within-relation shuffle used by the RMIT control to `data/codex_graph.json`:

| Condition | Accuracy | Δ vs baseline | Prediction change rate |
| --- | ---: | ---: | ---: |
| Baseline | 44.00% | — | — |
| Shuffled, seed 11 | 42.40% | −1.60 | **2.60%** |
| Shuffled, seed 23 | 42.80% | −1.20 | **2.00%** |
| Shuffled, seed 37 | 42.60% | −1.40 | **3.00%** |
| All relations removed | 35.80% | −8.20 | 90.80% |

**Destroying every fact in the graph while preserving its structure changes 2–3% of predictions and
costs 1.2–1.6 accuracy points.** For comparison, the same class of destruction costs the
deterministic completeness component **42.4 points**. The emptied condition collapses to a constant
`Not-in-KG` (35.80% — precisely the majority floor), confirming the pipeline reacts to a relation
key's *presence* but not to its *content*.

**RQ1 is therefore answered negatively for the LLM pipeline on CoDEx**: its verdicts are almost
entirely recoverable without the graph's factual content. This is a stronger and cheaper result than
the full LLM destruction control the paper defers to future work, and it follows directly from
[§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure) —
a namespace mismatch is invariant to what the values actually say.

The 44.00% oracle-parsed baseline against the LLM pipeline's 41.80% also indicates the LLM
decomposition stage contributes ≈2 points on CoDEx over gold parsing.

### 5.4 New finding C — the FactKG subsample is severely unrepresentative

The paper flags prefix sampling as a threat but does not quantify it. `data/factkg_test.jsonl` is
**sorted into contiguous reasoning-type blocks** (45 blocks total; the first is `existence` × 375,
the second `num1|substitution` × 755). Consequences for the evaluated first-500 slice:

| Property | First 500 (evaluated) | Full 9,041 |
| --- | ---: | ---: |
| Reasoning types covered | **2 of 13** | 13 |
| `Supported` / `Contradicted` | 177 / 323 | 4,398 / 4,643 |
| Majority floor | **64.60%** | **51.35%** |

The subsample is 75% `existence` and 25% `num1|substitution`; the other eleven types — including
every negation and multi-hop variant — are **entirely absent**. The reported 64.60% floor is an
artifact of block ordering: the true FactKG test floor is 51.35%.

This does not change the 80.20% / 79.80% accuracies, but it changes their interpretation. "Clears
the majority floor by 15 points" is a statement about a 2-of-13-reasoning-type slice with an
inflated label prior, not about FactKG. **No FactKG conclusion in this study generalises to the
benchmark.**

By contrast the **CoDEx prefix sample is benign**: that file is label-interleaved (660 label blocks
over 1,000 rows), and the first-500 distribution (155 / 166 / 179) closely tracks the full set
(333 / 333 / 334). The sampling threat is dataset-specific, not uniform.

### 5.5 New finding D — CoDEx `Not-in-KG` is decidable without reasoning, but the pipeline forfeits it

All 179 gold-`Not-in-KG` rows genuinely lack the edge in `data/codex_graph.json` (62 edge-absent,
20 relation-absent, 97 subject-missing). **54.2% are trivially decidable — the subject is not in
the graph at all.**

The pipeline nonetheless recovers only 43.6% (azure) / 72.1% (gemma) of the class, because
`link_entity`'s bi-encoder fallback has **no entity-level rejection threshold**: all 97 absent
subjects are linked anyway to some wrong entity. The pipeline never abstains on the grounds of an
unresolvable subject — it fabricates a subject, then adjudicates against the wrong record.

### 5.6 Answering the research questions

| RQ | Verdict | Basis |
| --- | --- | --- |
| **RQ1 Grounding** | Affirmative for the deterministic completeness component (42–52 point destruction delta). **Negative for the LLM pipeline on CoDEx** (2–3% prediction change under full content destruction). Untested on RMIT. | [§4.3](#43-per-dataset-detail), [§5.3](#53-new-finding-b--the-llm-pipeline-is-not-graph-grounded-on-codex-rq1-answered) |
| **RQ2 Transfer** | Negative. RMIT 97.3% → CoDEx 41.8%. Both endpoints are compromised — RMIT by circularity, CoDEx by the namespace bug — so the true gap is unmeasured, but the failure is now *localised* to stage-3 object handling rather than diffuse. | [§2.3](#23-rmit-claim-set--construction-and-circularity), [§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure) |
| **RQ3 Abstention** | The pipeline abstains substantially (FactKG coverage 40–57%) with the expected inverse coverage/accuracy relationship. Binary benchmarks structurally cannot score it. | [§4.3](#43-per-dataset-detail) |
| **RQ4 Measurement validity** | Negative, and the study's principal result. One harness converts exceptions into majority-class predictions; another disables self-consistency by a silent size threshold; a third mints gold labels with the system under test; a fourth evaluates a non-random 2-of-13 slice. | [§4.2](#42-the-stage-3-defect), [§1](#1-system-under-evaluation), [§2.4](#24-rmit-completeness-benchmark-and-its-control), [§5.4](#54-new-finding-c-the-factkg-subsample-is-severely-unrepresentative) |

---

## 6. Contributions

1. **A confirmed, reproduced, and repaired implementation defect that silently inflated a benchmark
   cell.** 113 crashes (22.6% of FactKG rows) were converted by the harness into 111 scored-correct
   predictions because the substituted default label coincided with the majority class. Reproduced
   deterministically with a stub LLM; repaired; regression tests added (23 → 25). Quantified
   before/after. ([§4.2](#42-the-stage-3-defect))

2. **Root-cause identification of the CoDEx class collapse.** Not an entity-linking failure — a
   subject/object **namespace asymmetry**. The graph keys entities by Q-id and stores object values
   as labels (17,203 / 17,203), while stage 3 links both positions into Q-id space. 96% of rows are
   excluded from `Supported` before the graph is consulted. This corrects the prior diagnosis and
   redirects the fix. ([§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure))

3. **A graph-destruction control run against the LLM pipeline's verification path**, previously
   listed as unrun. Full content destruction changes 2–3% of predictions versus 42.4 points for the
   deterministic component — answering RQ1 negatively for the pipeline on CoDEx.
   ([§5.3](#53-new-finding-b--the-llm-pipeline-is-not-graph-grounded-on-codex-rq1-answered))

4. **A quantified sampling-representativeness audit.** The FactKG prefix sample covers 2 of 13
   reasoning types and carries a 64.60% majority floor against the full set's 51.35%; the CoDEx
   prefix sample is benign. Converts a generic caveat into a bounded, dataset-specific claim.
   ([§5.4](#54-new-finding-c-the-factkg-subsample-is-severely-unrepresentative))

5. **An empirical nondeterminism floor** for this setup — 2.0–9.6% prediction flips (mean 5.75%)
   between identical reruns — measured in cells where the code change is provably unreachable,
   establishing a resolution limit for all engine comparisons. ([§4.4](#44-run-to-run-reliability))

6. **A source-level audit of four circularity and instrumentation problems**: RMIT verifies a
   template interpolated from the fields it queries; the completeness control mints gold labels with
   the system under test; FactKG collapses abstention into falsehood; self-consistency is silently
   disabled below 50 entities.

7. **Reproducible row-level analysis tooling** (`scripts/summarize_rerun_results.py`,
   `scripts/compare_runs.py`) that reconstructs every aggregate from saved predictions — the
   mechanism by which all of the above was verified rather than asserted.

8. **A working evidence-quarantine discipline** (`experiments/registry.json`) that correctly
   withheld `validated` status from every headline artifact, including the current one.

---

## 7. Corrections to the existing write-up

`docs/benchmarks/rerun_20260725_paper.md` is arithmetically sound; these are attribution and
interpretation corrections arising from [§5](#5-analysis).

| § | Current claim | Correction |
| --- | --- | --- |
| 6.3 | "consistent with entity/relation linking failing against the 1,182-entity CoDEx graph" | Subject linking succeeds **155/155**. The cause is object-side namespace conversion. |
| 6.3 | "Precision of 1.000 … indicates the verification logic is sound where linking succeeds" | Precision 1.000 is an artifact of *which* objects escaped Q-id conversion, not evidence of soundness. |
| 6.3 | CoDEx "carries the registry finding `invalidated_heldout_edges_present`" | That finding attaches to `data/codex_s_tri.jsonl` (from `generate_tristate_benchmarks.py`). The runs used `data/codex_test.jsonl` + `data/codex_graph.json`, where **all 179 `Not-in-KG` rows genuinely lack the edge**. The real CoDEx data problem is different — see [§5.5](#55-new-finding-d--codex-not-in-kg-is-decidable-without-reasoning-but-the-pipeline-forfeits-it). |
| 8.3, 10 | RQ1 "unanswered for the LLM pipeline"; next step 2 defers the control | The control is runnable on the deterministic stage-3/4 path and **answers RQ1 negatively for CoDEx**. |
| 8.3 | "Prefix sampling … need not be representative" | Quantified: FactKG covers **2 of 13** reasoning types with a floor inflated from 51.35% to 64.60%. CoDEx sampling is benign. |
| 10, step 3 | "Diagnose CoDEx `Supported` recall, beginning with entity linking" | Entity linking is not the fault. Fix object-position namespace handling in `stage_3_map_claim_to_triple`. |

---

## 8. Limitations

### 8.1 Construct validity

* **RMIT circularity.** `eval_rmit.py:54` verifies a template interpolated from the fields the
  verifier queries; the paraphrase is never evaluated. Measures round-tripping, not advising
  quality. The 97.3% figure cannot support a deployment claim.
* **Control circularity.** The completeness control's gold labels are minted by the system under
  test. Its 100% baseline is guaranteed; only the destruction delta is informative.
* **FactKG label collapse.** Abstention is scored as falsehood, so the benchmark cannot measure the
  system's distinguishing capability. `Not-in-KG` has support 0 by construction.
* **Occupancy is not completeness.** CWA/OWA routing keys on local field population, which says
  nothing about world coverage. On a sparse graph a relation can look "closed" merely because the
  few records present all have the field.
* **The routing claim is barely exercised.** On CoDEx the value-mismatch branch fires before
  world-assumption dispatch, so `world_assumption` is `None` on essentially every row.

### 8.2 Internal validity

* **Instrumentation converts failures into scores — still unfixed.** The stage-3 defect is repaired;
  the harness behaviour that concealed it (`eval_harness.py:277-288`) remains.
* **Object-namespace defect unfixed.** [§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure).
  All CoDEx numbers are measurements of a broken configuration.
* **No entity-level rejection threshold.** `link_entity`'s bi-encoder fallback resolves absent
  subjects to wrong entities rather than abstaining ([§5.5](#55-new-finding-d--codex-not-in-kg-is-decidable-without-reasoning-but-the-pipeline-forfeits-it)).
* **Confounded self-consistency.** `decomposition_agreement` is a hardcoded 1.0 on FactKG and a
  measured value on RMIT/CoDEx, so it is not comparable across datasets and propagates into
  confidence.
* **Uncalibrated confidence.** Coverage and selective accuracy are descriptive only. The
  `DualRiskController` is never exercised.
* **Nondeterminism.** One run per cell against a 5.75% mean flip rate.

### 8.3 External validity

* **Prefix sampling.** FactKG severely unrepresentative; CoDEx acceptable
  ([§5.4](#54-new-finding-c-the-factkg-subsample-is-severely-unrepresentative)).
* **Two engines, one institution, one advising intent** (`all_prerequisites`). No prerequisite
  Boolean structure (`AND`/`OR`/alternatives) is modelled. `azure-5-mini` was dropped post-fix.
* **50-course graph.** RMIT sits exactly at the `< 50` self-consistency boundary; a graph one course
  smaller would silently change its measurement regime.
* **Single reviewer.** The audit design supports source correction but not inter-annotator
  agreement; 20 calibration/test courses remain `awaiting_review`.

### 8.4 Statistical conclusion validity

* **Intervals are anti-conservative.** IID row bootstraps ignore subject clustering; true intervals
  are wider. Rows lack a subject-entity field, so clustered intervals are not computable.
* **No multiplicity correction** across six cells and many per-class comparisons. Treat individual
  comparisons as exploratory.
* **No paired significance test between engines.** Differences are described, not tested.
* **One cell is indistinguishable from the floor.** CoDEx / `gemma-4-e4b`'s interval
  [32.60%, 41.60%] contains 35.80%.

---

## 9. Prioritised next steps

Reordered by expected information gain per unit of effort.

1. **Fix object-position namespace handling in `stage_3_map_claim_to_triple`.** Compare in label
   space, or normalise graph values to Q-ids — not both. Every CoDEx number is currently a
   measurement of this bug. *Highest value; no model required.*
2. **Make crashes non-scoring in `eval_harness.py`.** Record an explicit non-scored outcome instead
   of substituting a class label. Independent of any model, and the flaw that hid defect #1.
3. **Add an entity-level rejection threshold to `link_entity`,** so unresolvable subjects abstain
   rather than link to a wrong record.
4. **Re-evaluate CoDEx after 1–3,** and re-run the destruction control from
   [§5.3](#53-new-finding-b--the-llm-pipeline-is-not-graph-grounded-on-codex-rq1-answered) as the
   acceptance test: a repaired pipeline must show a large destruction delta.
5. **Replace prefix sampling with seeded random sampling.** FactKG's block ordering makes
   `data[:limit]` actively misleading.
6. **Replicate each cell ≥3 times and report dispersion.** A 5.75% flip rate makes single runs
   inadequate.
7. **Re-emit rows with subject-entity ids** so clustered intervals become computable.
8. **De-circularize RMIT:** verify `text` rather than `raw_claim`, or author an independent response
   set. Complete the advisor audit for the 20 outstanding courses.
9. **Run the destruction control against the RMIT LLM pipeline** — still genuinely unmeasured.
10. **Remove or document `--seed` in `eval_rmit.py`,** which does not make runs reproducible.

---

## 10. What may and may not be claimed

**Supported by these artifacts.**

1. The stage-3 defect existed, is reproducible, is repaired, and inflated a benchmark cell by
   converting 113 crashes into 111 scored-correct predictions.
2. The deterministic completeness component is graph-sensitive: structure-preserving content
   destruction costs 42–52 points, all intervals excluding zero.
3. On CoDEx the pipeline reaches `Supported` for 0.6–3.9% of genuinely supported claims, and the
   cause is object-position namespace conversion, not entity linking.
4. The CoDEx verification path is **not** graph-grounded: full content destruction changes 2–3% of
   predictions.
5. Paired reruns under identical settings flip 2.0–9.6% of predictions.
6. FactKG's forced-binary protocol cannot measure abstention.
7. The evaluated FactKG slice covers 2 of 13 reasoning types with a majority floor inflated by 13
   points relative to the full test set.

**Not supported.**

1. That the system performs advising-quality verification — RMIT is circular.
2. Any CoDEx performance claim — those cells measure a broken object-mapping configuration.
3. Any FactKG claim that generalises to the FactKG benchmark — the sample is a non-random 2-of-13
   slice.
4. Any ranking of the two engines on FactKG (0.4 points, below the 5.75% noise floor).
5. Any calibration, risk-control, or deployment claim — confidence is uncalibrated by design and no
   calibration split was used.
6. That the 1.2-point post-fix delta shows the defect was harmless.
7. That per-relation world-assumption routing (claim C1) has been evaluated — on CoDEx the
   value-mismatch branch pre-empts routing entirely.

---

## 11. Reproduction

Environment: Python 3.13.5, `.venv` at repository root. Regression suite: **25 tests, all passing**
(verified).

```powershell
Set-Location C:\Users\Admin\Desktop\crawler
& .venv\Scripts\python.exe -m unittest discover -s tests

# Recompute every aggregate in §4 from saved row-level predictions
& .venv\Scripts\python.exe scripts\summarize_rerun_results.py `
    --dir output\experiments\rerun_20260725_fixed `
    --out output\experiments\rerun_20260725_fixed\aggregate_summary.json

# Paired pre/post comparison (§4.2, §4.4)
& .venv\Scripts\python.exe scripts\compare_runs.py `
    --before output\experiments\rerun_20260725 `
    --after output\experiments\rerun_20260725_fixed

# Deterministic completeness control (§4.3)
& .venv\Scripts\python.exe scripts\run_graph_destruction_control.py `
    --rows output\experiments\rerun_20260725_fixed\rmit_graph_control.rows.jsonl `
    --summary output\experiments\rerun_20260725_fixed\rmit_graph_control.summary.json

# Confirm crash counts (113 / 30 pre-fix, 0 post-fix)
Get-ChildItem output\experiments\rerun_20260725\*.log |
    ForEach-Object { "{0}: {1}" -f $_.Name,
        (Select-String -Path $_.FullName -Pattern "'bool' object is not callable").Count }
```

> Note: the logs are UTF-16LE. `Select-String` handles this via the BOM; a plain POSIX `grep` will
> report 0 matches on every file and appear to show no crashes. Use the PowerShell form above.

The four diagnostics in [§5.2](#52-new-finding-a-the-codex-supported-collapse-is-an-object-namespace-bug-not-a-linking-failure)–[§5.5](#55-new-finding-d--codex-not-in-kg-is-decidable-without-reasoning-but-the-pipeline-forfeits-it)
were run ad hoc against `VerificationPipeline` with a stub LLM and are **not yet committed as
scripts**; they should be added under `scripts/` before any of their findings is promoted beyond
`candidate`.

### Artifact inventory

| Artifact | Path |
| --- | --- |
| Post-fix row-level predictions / logs | `output/experiments/rerun_20260725_fixed/*.json`, `*.log` |
| Process manifest (exit codes, UTC timestamps) | `output/experiments/rerun_20260725_fixed/process_manifest.json` |
| Recomputed aggregates | `output/experiments/rerun_20260725_fixed/aggregate_summary.json` |
| Control rows / summary (with graph, benchmark, script hashes) | `output/experiments/rerun_20260725_fixed/rmit_graph_control.*` |
| Pre-fix artifacts (defect case study) | `output/experiments/rerun_20260725/` |
| Registry status | `experiments/registry.json` |
| Authoritative narrative study | `docs/benchmarks/rerun_20260725_paper.md` |

`output/` is git-ignored; artifacts are local to the run machine.
