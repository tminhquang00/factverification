# Current Status

**Updated:** 2026-08-03
**Branch:** `codex/fix-data-generation-pipeline`
**Gold revision:** 2026-08-03c — declaration-independent gold, with set-relation depletion handling
**Study status:** automated end-to-end rerun complete under the revised gold
**Research status:** `candidate_automated` — not independently validated by humans
**Models:** hosted `azure-4.1-mini`; local `google/gemma-4-e4b` through LM Studio

## Read this first: a headline number was withdrawn

The earlier claim that the proposed `declared` route achieves a **zero false-contradiction rate** has
been withdrawn. It was circular.

The old gold function decided whether a missing fact counted as `Contradicted` or `Not-in-KG` by
reading a completeness declaration file. The proposed `declared` routing mode decided the same thing
by reading **the same file**. Different code, identical rule — so the system was being graded against
its own definition. It scored exactly 1.000 accuracy and 1.000 macro-F1 in all 336 experimental
cells, with a zero-width bootstrap interval. That is what a tautology looks like, not a result.

The reported `binary` baseline had the same defect. It was not a system; it was one line of
post-processing on the proposed system's output. Its famous "5.1% → 96.3%" curve was arithmetic: at
20% retention, 1105 gold `Not-in-KG` rows ÷ 1147 predicted contradictions = 0.963 exactly. That curve
restated how many facts we deleted and said nothing about any model.

**What was fixed:**

1. Gold now reads only two graphs — the undegraded reference snapshot and the damaged graph the
   system could see — and never opens a declaration file. See
   [`scripts/intervention_gold.py`](../scripts/intervention_gold.py).
2. `binary` is now a real routing mode that runs its own pass over the graph.
3. A new `declared_stale` arm models completeness metadata that was never updated after data loss.

**What the fix revealed:** the proposed route is no longer perfect. At 20% retention it scores 99.0%
accuracy and 0.919 macro-F1 — high, but no longer the flat 1.000 that signalled circularity. Its
residual error is now visible: 61.9% contradiction precision, from predicting 42 contradictions where
gold supports 26.

### A second correction

The first attempt at the new gold had its own bug, and the finding derived from it is **withdrawn**.

Random deletion removes *individual members* of a set relation and leaves the container behind
(`[ES2002, ES2660, IS2101, LC1016]` → `[ES2660]`). The first implementation tested only "is the field
present?", so it read the absence of a deleted member as a *contradiction* — even though the member
really is a prerequisite and vanished only because we deleted it. That mislabelled 230 of 296
supposed contradictions in one cell and produced a published claim that `declared_oracle`
"over-abstains, recovering only 14.2% of detectable contradictions". **That claim was false** — the
system was abstaining correctly and the answer key was wrong. Actual contradiction recall is
94.6–100%.

The invariant is now a test: gold must never label a reference-world truth `Contradicted`. Residual
anomalies across all 61,164 rows: **5**, all from one multi-hop triple, all handled conservatively.

## At a glance

| Area | Status | Meaning |
| --- | --- | --- |
| Gold independence | **Fixed** | Gold is a function of graphs only; no system under test defines it |
| Data and degradation pipeline | Complete | Fixed NUSMods/RMIT inputs, manifests, three seeds, random and clustered deletion |
| Long-form model matrix | Complete | Azure/Gemma self and cross-detector arms; saved answers reused across detectors |
| Baselines | Complete | `declared_oracle`, `declared_stale`, `binary`, occupancy, oracle-context Azure/Gemma, pinned MiniCheck |
| Transfer | Complete | NUSMods, RMIT, FactKG, CoDEx public cells for both models |
| Multi-vendor verifier panel | Complete | 15 models, 4 vendors; 17,993 of 18,000 classifications scored |
| Retrieval recall bound | Complete | BM25 over 11,647 records; bounds the oracle-context assumption |
| Engineering verification | Passing | **183 tests**; NUSMods/CoDEx destruction gates pass; 5 residual gold anomalies in 61,164 rows |
| Human validation | Intentionally skipped | Questions, declarations, and gold remain researcher/mechanically defined |
| Publication readiness | Thesis ready; workshop ready | Not journal-ready; see the comprehensive assessment |

## The metric to read

Two safety numbers appear in the reports, and the difference matters.

**False-contradiction rate (FCR)** — of the contradictions a system announced, how many were wrong?
Traditional, but it depends on the *convention* that absence should be labelled `Not-in-KG`. A
reader who rejects that convention can dismiss the number.

**Contradiction rate on true claims (CR-true)** — of the claims that are **true in the reference
world**, how many did the system call `Contradicted`? This needs no convention at all. There is one
defensible answer to "should you contradict something true?", and it is no.

> **CR-true is the headline safety metric.** FCR is retained only for comparability with prior work.

## Headline result

Contradiction rate on true claims, NUSMods random deletion, pooled across three seeds and all three
answer-generation conditions. Lower is safer.

| Generator → detector | System | 100% | 80% | 50% | 20% |
| --- | --- | ---: | ---: | ---: | ---: |
| Azure → Azure | `binary` | 0.0% | 15.4% | 39.3% | **66.4%** |
| Azure → Azure | `declared_stale` | 0.0% | 15.4% | 39.3% | **66.4%** |
| Azure → Azure | `declared_oracle` *(ceiling)* | 0.0% | 0.0% | 0.0% | 0.0% |
| Azure → Gemma | `binary` / `declared_stale` | 0.0% | 17.2% | 42.1% | 70.5% |
| Gemma → Azure | `binary` / `declared_stale` | 0.0% | 15.8% | 41.6% | 73.9% |
| Gemma → Gemma | `binary` / `declared_stale` | 0.0% | 17.3% | 43.7% | 76.1% |

Azure self-detection at 20% retention: 66.4%, clustered 95% interval `[62.8, 70.1]`, over 1,374
true-world claims.

**The key new finding is that the `declared_stale` and `binary` rows are identical**, in all four
pairings, at every retention level. Stale completeness metadata performs exactly as well as having no
metadata at all. The mechanism is simple: a relation declared complete whose facts have been deleted
forces closed-world routing, which is precisely what a metadata-free system does.

> Shipping a completeness field buys nothing unless it is re-derived whenever the data changes.

## What `declared_oracle` is and is not

`declared_oracle` receives a declaration regenerated for the exact damage applied, so every degraded
relation is correctly marked incomplete and absence always routes to `Not-in-KG`. It therefore
**cannot** produce a false contradiction.

> Its zero is a **ceiling, not a result** — it answers "what would perfectly maintained metadata
> buy?" and nothing more. It is never presented as beating the baselines.

It also is not free. At Azure self-detection, random 20% retention:

| Metric | Value |
| --- | ---: |
| Accuracy | 99.0% |
| Macro-F1 | 0.919 |
| `Contradicted` precision / recall | **0.619** / 1.000 |
| Decision coverage | 31.7% (vs 99.3% at full retention) |

It catches every contradiction gold supports. Its residual error runs the other way — 42 predicted
against 26 supported — and those 16 extra cases are claims genuinely false in the world whose
disconfirming evidence was deleted, so they are unjustified but harmless (CR-true stays 0.0%).

**The real price is coverage, not correctness.** The safe system answers roughly a third as often at
severe incompleteness. Whether finer-grained declarations would recover that coverage is an open
question this study does not settle.

## The 15-model panel: is correct abstention a capability, a quirk, or a floor?

The identical protocol — same claims, same oracle-selected evidence, same prompt, same
declaration-independent gold — run across 15 models from four vendors, nano to frontier. 18,000
classifications, of which 17,993 produced a prediction; the 7 failures (0.04%) are all
`gemini-2.5-flash` JSON truncations, excluded from scoring and never defaulted. Sorted by the
convention-free safety metric.

| Model | Vendor | Tier | acc@100 | acc@20 | **CR-true@20** | 95% CI | absP | absR |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.4-nano | OpenAI | small | 99.3% | **94.7%** | **5.1%** | [0.8, 10.8] | 100.0% | 93.3% |
| azure-4.1 | OpenAI | large | 95.3% | 80.7% | 11.2% | [5.5, 17.2] | 100.0% | 74.7% |
| gpt-5.4 | OpenAI | large | 98.7% | 87.3% | 12.7% | [6.8, 19.7] | 100.0% | 83.6% |
| claude-opus-4-7 | Anthropic | frontier | 100.0% | 83.3% | 18.1% | [10.2, 25.8] | 100.0% | 78.2% |
| gpt-5.4-mini | OpenAI | mid | 99.0% | 79.3% | 18.8% | [10.8, 26.8] | 99.4% | 72.9% |
| gpt-5.5 | OpenAI | frontier | 92.0% | 87.0% | 20.7% | [12.2, 28.0] | 97.2% | 80.6% |
| azure-4.1-mini | OpenAI | mid | 92.0% | 65.3% | 23.9% | [15.8, 31.6] | 100.0% | 54.2% |
| claude-haiku-4-5 | Anthropic | small | 92.7% | 69.7% | 24.3% | [16.4, 32.2] | 100.0% | 60.0% |
| azure-o3 | OpenAI | reasoning | 95.3% | 71.7% | 27.2% | [18.8, 35.1] | 100.0% | 62.7% |
| gemini-2.5-flash-lite | Google | small | 98.3% | 69.0% | 32.6% | [26.8, 39.0] | 98.5% | 59.6% |
| llama-3.3-70b | Meta | open | 92.0% | 59.3% | 32.6% | [24.2, 40.4] | 100.0% | 46.2% |
| gemini-2.5-pro | Google | large | 93.0% | 58.0% | 37.7% | [28.7, 46.2] | 100.0% | 44.4% |
| claude-sonnet-4-6 | Anthropic | mid | 92.0% | 55.3% | 39.5% | [30.7, 47.6] | 100.0% | 40.9% |
| gemini-2.5-flash | Google | mid | 92.7% | 52.2% | 44.0% | [37.0, 50.7] | 100.0% | 36.6% |
| azure-4o-mini | OpenAI | small | 76.3% | 42.7% | **54.0%** | [45.9, 61.6] | 100.0% | 26.7% |

**Four results:**

1. **The failure mode is uniformly under-abstention.** Abstention precision is 97.2–100% for *every*
   model — when a model says "I cannot tell", it is essentially always right to. The whole 10× spread
   comes from abstention recall (26.7%–93.3%). No model is over-cautious. Anything that pushes models
   toward more decisions makes this strictly worse.

2. **Binary-collapse harm is a constant of the task.** 68.1%–73.9% across all 15 models — a 5.8-point
   spread over a 10× capability range. Model choice is nearly irrelevant once the third label is
   removed; the entire 1.4×–14.3× benefit belongs to the model.

3. **Capability predicts harm weakly; idiosyncrasy dominates.** Spearman(competence, harm) = −0.66,
   but within-tier spread (48.9 points in the "small" tier) is ~4× the between-tier spread (13.2
   points), and the ordering is non-monotonic inside every vendor. `gpt-5.4-nano` (smallest in its
   family) beats `gpt-5.5` (frontier) fourfold. Vendor means: OpenAI 21.7%, Anthropic 27.3%, Meta
   32.6%, Google 38.1%.

4. **There is a floor and it is not zero.** Best model 5.1%, CI [0.8, 10.8] excluding zero; median
   24.3%; 14 of 15 above 11%. Under conditions deliberately generous to the model, no current model
   drives false contradiction of true statements to zero.

> Tri-state prompting is **necessary** (without it, 68–74% regardless of model), **not sufficient**
> (no model reaches zero), and **unpredictable from capability**. Waiting for better models is not a
> strategy — handle completeness explicitly in the system.

**Confound:** six models — `azure-o3`, `claude-opus-4-7`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`,
`gpt-5.5` — reject `temperature=0` and ran at a provider default. They span best to mid-pack and the
worst model overall ran at temperature 0, so this does not explain the ordering, but it is a real
limitation of comparing vendors through one gateway. Recorded per-model under `run.sampling`.

## Independent evidence: LLM verifiers with oracle context

These arms matter most, because the predictor has no connection to the gold definition.

| System | 100% | 80% | 50% | 20% random | 20% clustered |
| --- | ---: | ---: | ---: | ---: | ---: |
| Azure tri-state, CR-true | 0.0% | 7.6% | 18.8% | **25.4%** | 9.8% |
| Azure binary collapse, CR-true | 0.0% | 14.1% | 42.0% | **68.5%** | 72.5% |
| Gemma tri-state, CR-true | 10.9% | 22.8% | 44.6% | 67.0% | 58.3% |
| Gemma binary collapse, CR-true | 13.8% | 27.9% | 51.8% | 75.7% | 76.8% |
| MiniCheck mapped, CR-true | 22.5% | 33.0% | 55.1% | **80.8%** | 85.1% |

Two things are simultaneously true:

- **Tri-state prompting genuinely helps.** For Azure it cuts the harm 2.7× (68.5% → 25.4%) and holds
  accuracy at 64.3% where binary collapse falls to 24.7%.
- **It is not sufficient.** One in four true claims is still contradicted, and Azure's false-support
  rate simultaneously rises 8.0% → 33.3%, so the failure is not mere over-caution.

The benefit is also model-dependent: 2.7× for Azure but only 1.13× for Gemma, which already
contradicts 10.9% of true claims on a fully intact graph. Being able to use an "unknown" option is a
model-capability question, not something the prompt grants for free.

MiniCheck's *native* binary accuracy **rises** 71.3% → 83.3% as facts are deleted, while its
tri-state accuracy collapses to 17.0% and its CR-true reaches 80.8%. The metric it optimises improves
precisely as it becomes more dangerous — evidence that label space, not model quality, is the binding
constraint.

## Occupancy inference is not a substitute

Azure self-detection, random deletion, CR-true by threshold:

| Threshold | 100% | 95% | 90% | 80% | 50% | 20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 | 0.0% | 2.5% | 4.0% | 7.9% | **20.5%** | **0.0%** |
| 0.95 | 0.0% | 2.5% | 0.0% | 0.0% | 0.0% | 0.0% |

Harm rises to 20.5% at 50% retention, then falls to zero at 20%. Nothing improved — the relation
simply became sparse enough to cross the threshold and flip from closed to open in one step. Each
threshold flips at a different retention level, so there is no safe default.

## How generous is "oracle context"?

Every flat-context number above assumes the verifier is handed exactly the right record — recall@1 =
100% with perfect relation selection. A real BM25 retriever over all 11,647 records (stopword
removal, exact course-code promotion, optional dense rerank) achieves:

| Query mode | k=1 | k=5 | k=10 | k=50 |
| --- | ---: | ---: | ---: | ---: |
| Code-bearing (as generated) | **88.0%** | 98.0% | 98.0% | 100.0% |
| Title-only (code → course title) | **47.0%** | 76.0% | 85.5% | 98.5% |

So oracle context overstates available evidence by **~12 points at rank 1 when an identifier is
present, and ~53 points when it is not**. The dense rerank does not help (86.5% / 44.0%) — a negative
result worth reporting: on short catalogue records with a strong identifier signal, general-purpose
sentence embeddings add nothing over tuned BM25.

This corroborates the NIL linking finding from an independent direction. **Deployment
recommendation: preserve identifiers end-to-end.** Where they survive, the oracle-context numbers are
close to achievable; where only titles survive, discount every downstream verification number.

## Stage attribution: the verifier is not the bottleneck

| Generator → detector | Extraction coverage | Expected-triple F1 | Exact expected set | Stage 4 on extracted atoms |
| --- | ---: | ---: | ---: | ---: |
| Azure → Azure | 87.5% | 98.6% | 96.6% | 100.0% |
| Azure → Gemma | 80.0% | 91.1% | 79.0% | 100.0% |
| Gemma → Azure | 76.5% | 87.4% | 77.8% | 100.0% |
| Gemma → Gemma | 70.0% | 79.7% | 65.3% | 100.0% |

Oracle linking and verification are both 100%, and Stage 4 on correctly extracted atoms is 100% in
every pairing. Effort spent improving the symbolic verifier is wasted; effort spent on decomposition
and linking is not.

Cross-detector contrasts: swapping detector Gemma→Azure on identical answers gains 7.7 points;
swapping Azure→Gemma loses 7.5. Holding the detector fixed, Azure answers beat Gemma answers by
11.2–11.4 points.

## What retention percentages mean

`100/95/90/80/50/20%` are **nominal relation-fact retention targets** — not accuracy, confidence,
question coverage, or decomposition agreement. All 11,647 NUSMods modules remain in every graph; we
delete facts *about* modules, never modules.

| Retention | Approximate facts removed from each selected relation |
| ---: | ---: |
| 100% | 0% |
| 80% | 20% |
| 50% | 50% |
| 20% | 80% |

Selected relations are credits, faculty/school, prerequisites, preclusions, and offered semesters.
Staffing remains naturally incomplete and is never artificially degraded.

Random mode deletes individual facts and is exact to rounding. Clustered mode deletes department
groups, so realized retention varies with group size; every manifest records requested and realized
values per relation.

Separately, "two-pass self-consistency" means the detector runs twice at temperatures `0.1` and `0.2`
and keeps only claims appearing in both passes. It is unrelated to the retention percentage.

## Publication judgment

| Target | Readiness | Reason |
| --- | --- | --- |
| Master's thesis | **Yes, now** | Coherent methodology, controls, and both positive and negative findings, with an honest validity boundary. |
| Workshop / short paper | **Yes, now** | The gold fix removed the blocking defect; the remaining findings are independent measurements with clustered intervals. |
| Full conference | **Reachable in 6–8 weeks** | Needs human-validated gold on a stratified sample plus a real retriever. |
| Journal | **No** | Also requires natural incompleteness and repeated stochastic runs. |

Frame the paper as a **measurement paper** — "we measure how post-hoc verification degrades under KG
incompleteness" — not a systems paper claiming a better verifier. Systems papers are judged on
beating baselines, a fight this work would lose against the FActScore/SAFE/VeriScore lineage.
Measurement papers are judged on whether the measurement is sound and the finding is non-obvious,
which is where the strength actually lies.

## Important limitations

- Gold is now independent of the systems under test, but is still derived from graph contents rather
  than human judgement. A human study is the highest-value remaining item.
- `declared_oracle` cannot lose on the safety metric by construction; it is a ceiling throughout.
- The context-generation and flat-verifier arms use oracle subject/relation selection, not retrieval.
- One stochastic answer run is saved per generator/condition.
- Cross-detector decomposition is stochastic even when answer text is fixed.
- Occupancy is graph density, not real-world completeness, and behaves non-monotonically.
- Confidence is heuristic; calibration is descriptive, not conformal.
- RMIT is small; FactKG is binary and its apparent score moves 21.6 points with sampling method.
- Data-release rights for source catalogue records still require review.

## Next steps, prioritised

1. **Human-validated gold** on 300 stratified claims, two annotators, report Cohen's κ. One weekend.
2. **Replace oracle context with a real retriever** (BM25 + embedding rerank); report retrieval
   recall separately. About a day.
3. **Three or more answer-generation runs** per generator/condition, to cover LLM sampling variance.
4. **Fact-level or entity-level declarations**, addressing the 85.8% over-abstention in §4.3 of the
   comprehensive report.
5. **A naturally incomplete graph** — a time-sliced NUSMods snapshot pair gives real missingness from
   already-cached data.
6. **Scale the question set** to ~1,000. Do this last; it costs compute, not design.

## Sources of truth

- [Comprehensive final report](benchmarks/comprehensive_final_study_20260803.md) — results,
  uncertainty, analysis, literature boundary, publication decision.
- [Methodology of record](architecture/methodology.md) — implemented behaviour.
- [Benchmark construction](benchmark_construction.md) — source data and retention semantics.
- [Experiment runbook](experiment_runbook.md) — exact reproduction flow.
- [`experiments/registry.json`](../experiments/registry.json) — machine-readable artifact ledger.

Artifacts produced under the old declaration-coupled gold are retained on disk for forensic
comparison but are **not current evidence**. Any table showing a flat 0.0% false-contradiction rate
for a system named plain `declared`, or a 1.000 macro-F1, comes from those files and is withdrawn.
