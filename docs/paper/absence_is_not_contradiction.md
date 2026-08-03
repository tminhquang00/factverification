# Absence Is Not Contradiction: Measuring Post-Hoc Factuality Verification Under Knowledge-Graph Incompleteness

**Draft — 2026-08-03.** All figures in this paper are reproducible from the row-level artifacts listed
in Appendix A. Gold revision `2026-08-03c`; regression suite 183 tests.

---

## Abstract

Post-hoc factuality verification systems check long-form model output against a knowledge source. When
that source is a knowledge graph, the graph is incomplete, and a claim's evidence is simply *missing*,
a verifier must choose between saying the claim is **contradicted** and saying it is **unverifiable**.
Systems that lack the second option — or that believe their source is complete when it is not — convert
missing evidence into confident false accusations.

We measure how large that error becomes. We take a fixed 11,647-entity university catalogue graph, delete
relation facts under controlled random and clustered protocols across six retention levels and three
seeds, and evaluate verification against a gold standard computed **only** from the undegraded reference
graph and the damaged graph the system was allowed to see — never from the completeness metadata any
system under test consumes. This independence is the paper's central methodological requirement: an
earlier version of this study derived gold from the same declaration file the proposed system read, and
consequently reported a perfect 1.000 accuracy and macro-F1 in all 336 experimental cells. That result
was a definition restating itself, and it is withdrawn here.

Under the corrected protocol we report four findings. First, across **15 models spanning four vendors and
a nano-to-frontier capability range** (18,000 classifications), a three-valued label space is *necessary
but not sufficient*: without it every model contradicts true claims at 68.1–73.9% under severe
incompleteness — a 5.8-point spread over a 10× capability range — while with it the rate spans 5.1–54.0%
and **no model reaches zero** (best 5.1%, 95% CI [0.8, 10.8]; median 24.3%). Second, the failure mode is
**uniformly under-abstention**: abstention precision is 97.2–100% for every model, and the entire spread
is in abstention recall (26.7–93.3%). Third, correct abstention **does not track capability**: within-tier
variation (48.9 points) is roughly four times between-tier variation (13.2 points), and the ordering is
non-monotonic inside every vendor. Fourth, completeness metadata helps only if maintained: a declaration
written for the healthy catalogue and never updated performs *identically to no metadata at all*, matching
the metadata-free baseline to the decimal in all four generator/detector pairings at every retention level.

We frame this as a measurement paper. We do not claim a better verifier, and we report the arm that
receives perfectly synchronised metadata as a definitional ceiling rather than a result.

---

## 1. Introduction

Long-form answers from language models are commonly checked after the fact by decomposing them into
atomic claims and verifying each claim against a retrieved source. When the source is a knowledge graph,
verification reduces to a lookup: does the graph contain this triple?

The difficulty is what a *failed* lookup means. A graph that does not record a course's credit value may
be recording that the course has no credits, or may simply not know. Under a closed-world assumption the
absence is a refutation; under an open-world assumption it is ignorance. Real knowledge graphs are
partially complete: a university catalogue authoritatively lists prerequisites but not who teaches each
module. The correct assumption therefore varies *per relation*, and it varies *over time* as data is lost,
migrated, or never ingested.

The practical consequence is asymmetric. A verifier that wrongly says "unverifiable" wastes an
opportunity. A verifier that wrongly says "contradicted" tells a user that a true statement is false. In an
advising, compliance, or medical setting the second error is the one that causes harm, and it is the one
that grows as the source degrades.

Prior work establishes atomic decomposition and evidence-grounded checking, and separately establishes
that knowledge graphs are incomplete and that completeness can be declared as metadata. What is rarely
done is to treat source completeness as a **controlled experimental variable** and measure how
verification behaviour changes as it is varied, using an error metric that is asymmetric by construction.

### 1.1 Contributions

**C1 — A declaration-independent gold standard for incompleteness experiments.** We define gold from two
graphs only: the reference (undegraded) snapshot, which stands in for the world, and the condition
(damaged) graph, which defines available evidence. No completeness declaration is consulted. This makes a
declaration a *system input* that can be correct, stale, or absent, and lets the score distinguish those
cases. §4.3 documents why this is necessary — including the circular result it replaces and a second bug
it initially concealed.

**C2 — A convention-free safety metric.** *Contradiction rate on true claims* (CR-true) is the fraction of
claims **true in the reference world** that a system labelled `Contradicted`. Unlike false-contradiction
rate it requires no convention about how absence ought to be labelled, so it remains interpretable to a
reader who rejects our labelling choices. §4.4.

**C3 — A 15-model, four-vendor measurement of abstention under incompleteness.** Identical claims,
evidence, prompt and gold across OpenAI, Anthropic, Google and Meta models from nano to frontier. This
separates three previously indistinguishable hypotheses — capability scaling, idiosyncrasy, and a
structural floor — and finds support for the latter two. §6.2.

**C4 — A decomposition of the harm into a task term and a model term.** Binary-collapse harm is
68.1–73.9% regardless of model; the tri-state benefit is 1.4×–14.3× and belongs entirely to the model.
§6.2, §7.1.

**C5 — Stale-metadata equivalence.** Completeness metadata that is not re-derived when data changes has the
safety profile of no metadata at all, matching the metadata-free baseline to the decimal. §6.1.

**C6 — Quantified bounds on the study's own generosity.** Stage attribution isolates where end-to-end error
originates (§6.4), and a real BM25 retriever bounds how optimistic the oracle-context protocol is:
88.0% recall@1 with identifiers present, 47.0% without, against an assumed 100% (§6.5).

### 1.2 What we do not claim

We do not claim a state-of-the-art verifier, independently validated real-world factuality accuracy
(our gold is mechanical, not human-annotated), realistic end-to-end retrieval performance, or calibrated
deployment safety. §8 states these limits in full.

---

## 2. Related work

**Atomic decomposition and evidence-grounded factuality.** FActScore, SAFE, RefChecker and VeriScore
establish the decompose-then-verify paradigm for long-form output. These systems are largely agnostic to
whether the evidence source is complete; retrieval failure and source absence are generally folded into a
single "unsupported" outcome.

**Efficient binary fact checking.** MiniCheck optimises the sentence-level supported/unsupported decision.
Our results are not a criticism of that objective: MiniCheck's *native* binary accuracy actually rises as
we delete facts (71.3% → 83.3%), because missing-evidence documents become easier to call unsupported. The
issue is that a two-valued label space cannot express the third outcome the open-world setting requires,
so the same behaviour that improves its native metric is what makes it unsafe here (§6.3).

**Fact verification over knowledge graphs.** FactKG studies claim verification against graph evidence. We
use it only as a portability check, and report a methodological caution: its examples are ordered by
reasoning type, so prefix sampling gives 82.0% where random sampling gives 60.4% for the same model — a
21.6-point artifact of sampling composition, independently reproduced on a second model (§6.6).

**Completeness statements and partial closed-world reasoning.** Darari et al. and subsequent work on
fine-grained completeness statements formalise declaring which parts of a knowledge base are complete, and
a recent survey covers KG completeness and recall. Recent KG-RAG work studies retrieval over incomplete
graphs. "Knowledge graphs are incomplete" is therefore not a novel observation and we do not present it as
one.

**The gap.** Long-form post-hoc factuality work rarely treats source completeness as explicit metadata whose
*controlled degradation* is evaluated through *asymmetric* false-contradiction risk, and rarely distinguishes
fresh metadata from stale metadata as an experimental variable. That intersection is what we measure.

---

## 3. Problem formulation

Let `G*` be a reference knowledge graph standing in for the world, and `G ⊆ G*` the graph a verifier can
see. For a claimed triple `t = (s, r, o)` we define two independent properties.

**World truth**, established against `G*`:

- `true` — `G*` asserts `t`;
- `false` — `G*` asserts some value for `(s, r)` and it is not `o`;
- `unknown` — `G*` is silent about `(s, r)`.

**Evidence state**, established against `G`:

- `confirming` — `G` asserts `t`;
- `conflicting` — `G` asserts a different value for `(s, r)`;
- `absent` — `G` asserts nothing for `(s, r)`.

A verifier outputs one of `Supported`, `Contradicted`, `Not-in-KG`, `Out-of-scope`. The question this paper
studies is what a verifier should and does output when `evidence_state = absent`, as `G` is made
progressively sparser relative to `G*`.

The harm we measure is the pair (`world_truth = true`, prediction = `Contradicted`): the system asserts
that a true statement is false. This is the only cell of the confusion matrix whose wrongness requires no
argument.

---

## 4. Methodology

### 4.1 Verification pipeline

The system is post-hoc. It receives prose, and:

1. **Decomposes** it into `{subject, relation, object, claim_type}` atoms via a schema-guided prompt, called
   twice at temperatures 0.1 and 0.2, retaining only atoms whose normalised triple agrees across both
   passes ("two-pass self-consistency").
2. **Links** subjects through a cascade: exact identifier → normalised label or `code + title` →
   `all-MiniLM-L6-v2` cosine similarity → token-overlap fallback → NIL. Relations are normalised through
   conservative schema-gated aliases (so "worth four credits" maps to the credit relation without
   rewriting open-domain predicates such as "net worth").
3. **Verifies** each triple with relation-specific symbolic logic: scalar equality, set membership,
   prerequisite paths, explicit empty sets, and numeric normalisation.
4. **Routes absence** according to the configured completeness treatment (§4.2).
5. **Aggregates** by severity, `Contradicted` before `Not-in-KG` before `Out-of-scope` before `Supported`.

Explicit empty sets are load-bearing: the parser writes `"prerequisites": []` deliberately, so "this course
has no prerequisites" remains distinguishable from "prerequisite information is unavailable". Degradation
removes keys rather than emptying them, preserving that distinction.

### 4.2 Completeness routing — the independent variable

Four treatments, each executed as its own pass over the graph. None is derived from another by relabelling.

| Arm | Metadata received | Can it contradict from absence? | Role |
| --- | --- | --- | --- |
| `declared_oracle` | Declaration regenerated for the exact damage applied | No | **Ceiling** |
| `declared_stale` | Declaration for the *healthy* snapshot, never updated | Yes | Realistic deployment |
| `binary` | None; no third label exists at all | Yes | Floor |
| `occupancy_τ` | Inferred from observed relation density at threshold τ | Yes | Metadata-free heuristic |

`binary` collapses every `Not-in-KG` the symbolic core would produce — including those caused by an
unresolvable entity — into `Contradicted`, modelling an external two-valued checker.

**We state plainly that `declared_oracle` cannot lose on the safety metric.** Its declaration is
regenerated for the damage we caused, so absence always routes to `Not-in-KG` and CR-true is 0 by
construction. It answers "what would perfectly maintained metadata buy?" and is reported as a ceiling
everywhere it appears, never as a win over baselines. The scientific content lies in the arms that *can*
contradict from absence and do not define gold.

### 4.3 Declaration-independent gold

**This is the paper's key methodological requirement, and it exists because we got it wrong twice.**

*The circularity.* Our first gold function decided whether an absent fact was `Contradicted` or
`Not-in-KG` by reading the relation's entry in a completeness declaration file — the same file the proposed
`declared` routing mode read, with the same branch structure. The two were written as separate code, but
they were one definition. The proposed system consequently scored:

```
accuracy 1.000    macro-F1 1.000
Supported F1 1.000 | Contradicted F1 1.000 | Not-in-KG F1 1.000
clustered bootstrap 95% CI on accuracy: [1.000, 1.000]
```

in all 336 experimental cells. A zero-width interval on a perfect score is the signature of a tautology.
The reported binary baseline had the mirror defect: it was one line of post-processing on the proposed
system's output, so its headline curve was arithmetic — at 20% retention, 1105 gold `Not-in-KG` rows ÷
1147 predicted contradictions = 0.963, exactly the figure reported. That curve re-described the deletion
rate and would have been identical with a random verifier.

*The replacement.* Gold is now a function of `G*` and `G` alone. No declaration is opened.

| `world_truth` | `evidence_state` | Gold | Rationale |
| --- | --- | --- | --- |
| `true` | `confirming` | `Supported` | Evidence present. |
| `true` | `absent` | `Not-in-KG` | Claim is true and we deleted the proof. Contradicting it is the harm under study. |
| `false` | `conflicting` | `Contradicted` | Visible graph carries an incompatible value. |
| `false` | `absent` | `Not-in-KG` | The disconfirming value is gone; nothing visible licenses a contradiction. |
| `unknown` | `absent` | `Not-in-KG` | Natural open-world absence. |

`true`/`conflicting` cannot arise, since deletion only removes facts. Rows hitting it are flagged as
anomalies and, in strict mode, raise.

*The second bug.* Random deletion removes **individual members** of set-valued relations and leaves the
container behind: a reference prerequisite list `[ES2002, ES2660, IS2101, LC1016]` becomes `[ES2660]`. Our
first implementation of the replacement tested only "is the field present?", treated the shrunken list as
authoritative, and read the absence of `ES2002` as a *contradiction* — although `ES2002` genuinely is a
prerequisite and is missing only because we deleted it. This mislabelled **230 of 296** supposed
contradictions in a single cell and produced a published claim that the proposed route "over-abstains,
recovering only 14.2% of detectable contradictions". That claim was false: the system was abstaining
correctly and the answer key was wrong. Its actual contradiction recall is 94.6–100%.

The rule now applied: for a set relation, absence of a claimed member licenses `conflicting` **only when
the visible member set is provably identical to the reference member set**. Residual anomalies across all
61,164 scored rows: **5**, all from one multi-hop triple (`MA4262 → MA2108S`), all falling back to `absent`.

*The generalisable lesson.* A gold function that can label a reference-world truth as `Contradicted` is
broken. That invariant is now an executable test.

### 4.4 Metrics

| Metric | Definition | Convention-dependent? |
| --- | --- | --- |
| **CR-true** | Of claims with `world_truth = true`, the fraction predicted `Contradicted` | **No** — headline |
| False-contradiction rate | Of predicted contradictions, the fraction against non-`Contradicted` gold | Yes |
| Abstention precision | Of predicted `Not-in-KG`, the fraction where gold is `Not-in-KG` | Mildly |
| Abstention recall | Of gold `Not-in-KG`, the fraction predicted `Not-in-KG` | Mildly |
| Decision coverage | Fraction of atoms receiving a decision other than `Not-in-KG` | No |
| Tri-state accuracy, macro-F1 | Standard, over the three labels | Via gold |

CR-true is the headline because there is exactly one defensible answer to "should you contradict something
that is true?". Abstention precision and recall are reported alongside it because **CR-true is gameable**: a
system that answers `Not-in-KG` to everything scores zero while being useless. Precision exposes that
directly.

Intervals are clustered bootstrap (1,000 resamples) over `(deletion seed, question_id)` for the symbolic
arms and over `question_id` for the panel. Rates with zero predicted decisions are reported as `null`,
never as zero. Execution errors are excluded from the scored denominator and never replaced by a default
label.

---

## 5. Experimental design

### 5.1 Data

**NUSMods** — 11,647 module entities compiled from cached catalogue records. Each may carry a course code,
title, numeric credit value, school/faculty, prerequisite codes, preclusion codes, offered semesters, and
optional staffing fields. 200 deterministically generated questions over nine question types, yielding 300
distinct expected triples (124 prerequisite, 67 credit, 36 preclusion, 25 school, 24 semester, 24 staffing).

**RMIT** — 50 handbook-derived entities, 50 questions, 66 expected triples. A schema and language transfer
check, not the primary testbed.

**Public transfer** — FactKG and CoDEx, for portability and sampling sensitivity only.

Questions and expected triples are graph-derived, not human-annotated. This is a deliberate limitation
(§8).

### 5.2 Controlled degradation

Entities are never removed; only relation facts are. Degraded relations: credit value, faculty/school,
prerequisites, preclusions, offered semesters. **Staffing (`taughtBy`) is never degraded** — it is the
naturally incomplete open-world anchor.

Nominal retention `100/95/90/80/50/20%` denotes the fraction of facts remaining *in each degraded
relation*. It is not a fraction of questions, entities, or accuracy. Three seeds (`20260802/3/4`) and two
modes:

- **Random** — samples individual facts; exact to integer rounding.
- **Clustered** — removes department groups; realized retention departs from nominal (one nominal
  clustered 80% graph retained 82.2% of credit facts but 68.5% of preclusion facts).

Every condition records requested and realized retention per relation, source and output hashes, the seed,
and the full list of deleted triples.

The intervention shifts the gold distribution substantially, which is the point of the design. For the
Azure self-detection arm under random deletion:

| Retention | Gold `Supported` | Gold `Contradicted` | Gold `Not-in-KG` |
| ---: | ---: | ---: | ---: |
| 100% | 1374 | 222 | 12 |
| 80% | 1163 | 148 | 297 |
| 50% | 834 | 66 | 708 |
| 20% | 461 | 26 | 1121 |

### 5.3 Long-form generator/detector matrix

Answers are generated under three evidence conditions — `closed_book`, `rag_full`, `rag_degraded` (50%
retention) — at temperature 0.2, then decomposed and verified. Four pairings reuse **identical saved answer
text** across detector arms:

| Generator | Detector | Purpose |
| --- | --- | --- |
| `azure-4.1-mini` | `azure-4.1-mini` | Hosted self-detection |
| `google/gemma-4-e4b` | `google/gemma-4-e4b` | Local self-detection |
| `azure-4.1-mini` | `google/gemma-4-e4b` | Detector effect, answers fixed |
| `google/gemma-4-e4b` | `azure-4.1-mini` | Detector effect, answers fixed |

Decomposition remains stochastic even with fixed answers, so these are informative contrasts rather than
deterministic paired causal estimates.

### 5.4 The 15-model verifier panel

To test whether abstention behaviour is a capability, a quirk, or a floor, we run one arm — the
oracle-context tri-state verifier — across 15 models under an identical protocol. Only the model varies.

| Vendor | Models |
| --- | --- |
| OpenAI | `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `azure-4.1`, `azure-4.1-mini`, `azure-4o-mini`, `azure-o3` |
| Anthropic | `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5` |
| Google | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |
| Meta | `llama-3.3-70b` |

300 expected triples × 4 retention levels (100/80/50/20, random, seed 20260803) × 15 models = **18,000
classifications**. The model receives the relation-specific graph record and is instructed that
`Not-in-KG` is available when evidence does not settle the claim. Requested temperature 0.

This arm is chosen deliberately: the predictor is an LLM and gold comes from graph contents alone, so the
model has no influence whatsoever over its own answer key. It is the cleanest independent measurement in
the study.

*Yield.* 17,993 of 18,000 produced a prediction. The 7 failures (0.04%) are all `gemini-2.5-flash` responses
whose JSON was truncated mid-token, affecting 5 unique triples and leaving that model's cells at n=295–300.
Failed rows are excluded from scoring and never defaulted.

*Sampling confound.* Six models — `azure-o3`, `claude-opus-4-7`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`,
`gpt-5.5` — reject `temperature=0` and ran at a provider default. Each artifact records its resolved
sampling. §7.4 discusses why this does not explain the observed ordering but is nonetheless a real limit on
cross-vendor comparison through a single gateway.

### 5.5 Controls

Deterministic ceilings (gold triple → verifier; gold triple → linker → verifier), graph-value shuffling,
empty-graph destruction, and NIL threshold sweeps. Shuffled-graph prediction change must exceed 0.20.

---

## 6. Results

### 6.1 Symbolic routing: stale metadata is worth nothing

CR-true under random deletion, pooled over three seeds and all three answer-generation conditions.

| Generator → detector | System | 100% | 80% | 50% | 20% |
| --- | --- | ---: | ---: | ---: | ---: |
| Azure → Azure | `binary` | 0.0% | 15.4% | 39.3% | **66.4%** |
| Azure → Azure | `declared_stale` | 0.0% | 15.4% | 39.3% | **66.4%** |
| Azure → Azure | `declared_oracle` *(ceiling)* | 0.0% | 0.0% | 0.0% | 0.0% |
| Azure → Gemma | `binary` / `declared_stale` | 0.0% | 17.2% | 42.1% | 70.5% |
| Gemma → Azure | `binary` / `declared_stale` | 0.0% | 15.8% | 41.6% | 73.9% |
| Gemma → Gemma | `binary` / `declared_stale` | 0.0% | 17.3% | 43.7% | 76.1% |

Azure self-detection at 20% retention: 66.4%, clustered 95% CI [62.8, 70.1] over 1,374 true-world claims.
Clustered deletion reproduces the shape (0.0 → 15.9 → 45.1 → 69.4%).

**The `declared_stale` and `binary` rows are identical**, in all four pairings, at every retention level. The
mechanism is mechanical: a relation declared complete whose facts have been deleted forces closed-world
routing, which is exactly what a metadata-free system does. They can differ only on relations already
declared incomplete in the healthy snapshot (staffing) and on unresolvable entities — a small minority of
true-world claims.

> Shipping a completeness field buys nothing unless it is re-derived whenever the underlying data changes.

Paired difference, `declared_oracle` − `binary` at random 20%: accuracy **+68.3 points** [64.7, 71.6];
CR-true **−66.4 points** [−70.1, −62.7].

*Cost of the safe route.* `declared_oracle` at random 20% scores 99.0% accuracy, 0.919 macro-F1, and
`Contradicted` precision/recall of **0.619 / 1.000**. It catches every contradiction gold supports; its
residual error is 16 extra contradictions against claims that are false in the world but whose disconfirming
evidence was deleted — unjustified under certain-answer semantics, harmless on CR-true. The real price is
coverage: 99.3% → 82.5% → 57.5% → **31.7%** across 100/80/50/20% retention, while `declared_stale` holds
99.3% and `binary` 100%. **Safety is bought with abstention, not with accuracy.**

*Occupancy is not a substitute.* Inferring completeness from observed relation density is non-monotonic.
Azure self-detection, random deletion, CR-true:

| Threshold | 100% | 95% | 90% | 80% | 50% | 20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 | 0.0% | 2.5% | 4.0% | 7.9% | **20.5%** | **0.0%** |
| 0.70 | 0.0% | 2.5% | 4.0% | 7.9% | 0.0% | 0.0% |
| 0.85 | 0.0% | 2.5% | 4.0% | 0.0% | 0.0% | 0.0% |
| 0.95 | 0.0% | 2.5% | 0.0% | 0.0% | 0.0% | 0.0% |

Harm rises to 20.5% at 50% retention then collapses to zero at 20% — not because anything improved, but
because the relation finally became sparse enough to cross the threshold and flip from closed to open in
one step. Each threshold flips at a different retention level, so there is no safe default.

### 6.2 The 15-model panel

Results at random 20% retention, sorted by CR-true. `absP`/`absR` are abstention precision and recall.

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

**Binary-collapse harm is a constant.** Across all 15 models it falls in **68.1–73.9%** (mean 72.0%) — a
5.8-point spread over a 10× capability range.

**The failure mode is uniformly under-abstention.** Abstention precision is **97.2–100% for every model**.
Not one is over-cautious. The entire 10× spread in tri-state harm comes from abstention recall, 26.7–93.3%.

**No model reaches zero.** Best 5.1% with CI [0.8, 10.8] excluding zero; median 24.3%; 14 of 15 above 11%.

**Capability is a weak predictor.** Spearman(competence@100, CR-true@20) = **−0.66**;
Spearman(competence, abstention benefit) = **+0.69**. But:

| Grouping | Mean CR-true | Within-group range |
| --- | ---: | ---: |
| frontier | 19.4% | 2.6 pts (n=2) |
| large | 20.5% | 26.5 pts |
| reasoning | 27.2% | — (n=1) |
| small | 29.0% | **48.9 pts** |
| mid | 31.6% | 25.2 pts |
| open-weights | 32.6% | — (n=1) |
| OpenAI | 21.7% | 48.9 pts |
| Anthropic | 27.3% | 21.4 pts |
| Meta | 32.6% | — (n=1) |
| Google | 38.1% | 11.4 pts |

Between-tier mean spread is 13.2 points; within the "small" tier alone it is 48.9 — nearly four times
larger. Tier means are non-monotonic (mid is worse than small). And the ordering is non-monotonic **inside
every vendor**:

- OpenAI: `gpt-5.4-nano` (small) 5.1% beats `gpt-5.5` (frontier) 20.7% fourfold, while `azure-4o-mini`
  (also small) is worst in the panel at 54.0%.
- Anthropic: opus 18.1% < haiku 24.3% < sonnet 39.5% — the mid-tier model is weakest, not the smallest.
- Google: flash-lite (small) 32.6% < pro (large) 37.7% < flash (mid) 44.0%.

### 6.3 External verifier baselines

**Oracle-context LLM, hosted (`azure-4.1-mini`).** The model receives the exact records it needs and an
explicit tri-state instruction — a generous setting.

| Mode | Retention | Tri-state acc | **CR-true** | Binary-collapse acc | **Binary CR-true** | False-support |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 100% | 92.0% | 0.0% | 92.0% | 0.0% | 8.0% |
| Random | 80% | 83.3% | 7.6% | 77.7% | 14.1% | 10.7% |
| Random | 50% | 72.7% | 18.8% | 51.3% | 42.0% | 16.3% |
| Random | 20% | 64.3% | **25.4%** | 24.7% | **68.5%** | 33.3% |
| Clustered | 20% | 80.7% | 9.8% | 23.0% | 72.5% | 31.0% |

Tri-state prompting cuts harm 2.7× (68.5% → 25.4%) and holds accuracy at 64.3% where binary collapse falls
to 24.7%. It does not remove the harm, and the rising false-support rate (8.0% → 33.3%) shows the failure is
not mere over-caution — the model degrades in *both* directions as evidence thins.

**Local (`google/gemma-4-e4b`)** under the identical protocol: tri-state accuracy 87.3% → 36.7%, CR-true
10.9% → 67.0%; binary collapse 79.3% → 21.7%, CR-true 13.8% → 75.7%. The weaker model already contradicts
10.9% of true claims on a *fully intact* graph, and gains only 1.13× from the third label against the
hosted model's 2.7×.

**MiniCheck.** Native binary accuracy **rises** 71.3% → 83.3% as facts are deleted, because
missing-evidence documents become easy to call unsupported. Mapping `Unsupported → Contradicted`:

| Mode | Retention | Tri-state acc | **CR-true** | False-support |
| --- | ---: | ---: | ---: | ---: |
| Random | 100% | 71.3% | 22.5% | 10.1% |
| Random | 80% | 61.3% | 33.0% | 12.0% |
| Random | 50% | 40.0% | 55.1% | 18.9% |
| Random | 20% | 17.0% | **80.8%** | 33.8% |
| Clustered | 20% | 13.7% | **85.1%** | 36.9% |

The metric the checker optimises improves precisely as the checker becomes more dangerous. This is a
label-space defect, not a model-quality defect.

### 6.4 Stage attribution: the verifier is not the bottleneck

| Control | Result |
| --- | ---: |
| Gold triples → verifier | 100.0% |
| Gold triples → linker → verifier | 100.0% |
| Stage 4 on extracted atoms (all four pairings) | 100.0% |
| NUSMods shuffled-graph prediction change | 34.76% (gate 20%) |
| CoDEx shuffled-graph prediction change | 29.53% |
| RMIT shuffle / empty-graph accuracy drop | 42.4 / 51.5 pts |

Expected-triple metrics on full-context answers:

| Generator → detector | Extraction coverage | Expected-triple F1 | Exact expected set |
| --- | ---: | ---: | ---: |
| Azure → Azure | 87.5% | 98.6% | 96.6% |
| Azure → Gemma | 80.0% | 91.1% | 79.0% |
| Gemma → Azure | 76.5% | 87.4% | 77.8% |
| Gemma → Gemma | 70.0% | 79.7% | 65.3% |

Azure self-detection moves 23.2% (closed-book) → 63.0% (degraded context) → 98.6% (full context). Holding
answers fixed, swapping the detector Gemma→Azure gains 7.7 points; Azure→Gemma loses 7.5. Holding the
detector fixed, Azure answers beat Gemma answers by 11.2–11.4 points.

Since Stage 4 is at 100% in every pairing, effort spent on the symbolic verifier is wasted; the error budget
is dominated by decomposition and linking.

### 6.5 How generous is the oracle-context protocol?

Every oracle-context result assumes recall@1 = 100% with perfect relation selection. A real Okapi BM25
retriever over all 11,647 records (stopword removal, exact course-code promotion, optional
`all-MiniLM-L6-v2` rerank of the top 50):

| Query mode | k=1 | k=3 | k=5 | k=10 | k=20 | k=50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Code-bearing (as generated) | **88.0%** | 97.5% | 98.0% | 98.0% | 100.0% | 100.0% |
| Title-only (code → course title) | **47.0%** | 68.0% | 76.0% | 85.5% | 93.0% | 98.5% |

Oracle context therefore overstates available evidence by **~12 points at rank 1 when an identifier is
present and ~53 points when it is not**. The dense rerank does not help (86.5% / 44.0% at k=1) — on short
catalogue records with a strong identifier signal, general-purpose sentence embeddings add nothing over
tuned BM25. Reported as a negative result.

This corroborates the NIL linking result from an independent direction: on a 1,000-example title-only
held-out stress test at threshold 0.95, total exact/NIL accuracy is 57.2%, In-KB F1 48.4%, NIL F1 69.2%,
accepted-link coverage 38.8%. Course-code linking is perfect in the oracle arm.

### 6.6 Transfer and a sampling caution

| Dataset | Azure acc / macro-F1 | Gemma acc / macro-F1 |
| --- | ---: | ---: |
| RMIT (300 rows) | 97.0% / 98.2% | 75.0% / 80.3% |
| NUSMods (500 rows) | 99.8% / 99.8% | 99.4% / 99.4% |
| CoDEx (500 rows) | 84.8% / 84.5% | 79.8% / 79.7% |
| FactKG (500 rows) | 60.4% / 50.2% | 59.0% / 47.4% |

**FactKG exposes an evaluation pitfall worth reporting on its own.** Prefix sampling gives Azure 82.0%;
random sampling gives 60.4%. The 21.6-point gap is entirely sampling composition — FactKG is ordered by
reasoning type, so a prefix covers two ordered blocks with a 64.6% majority floor. The local run
independently reproduces this with a 23.4-point gap. Anyone benchmarking on FactKG should sample randomly
and say so.

RMIT reproduces the main pattern on a smaller graph: full-context expected-triple F1 78.8% (Azure) and
67.8% (Gemma), with Stage 4 and both oracle stages at 100%.

### 6.7 Selective risk

Held-out test split, Azure self-detection, 5% diagnostic false-contradiction target:

| System | Threshold | Contradictions accepted | Coverage | Observed risk | Binomial UB | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `binary` | 1.000 | 138 / 3,419 | 4.0% | 0.0% | 2.15% | 0.058 |
| `declared_stale` | 1.000 | 138 / 3,311 | 4.2% | 0.0% | 2.15% | 0.064 |
| `occupancy_0.85` | 1.000 | 138 / 934 | 14.8% | 0.0% | 2.15% | 0.091 |
| `declared_oracle` *(ceiling)* | 0.299 | 736 / 858 | 85.8% | 0.0% | 0.41% | 0.109 |

`declared_stale` again tracks `binary`: both discard ~96% of their contradiction decisions to reach the
target, while the oracle arm retains 85.8%. **Confidence gating cannot rescue stale metadata.** Note the ECE
column runs opposite to accuracy — the confidence score is heuristic and not fitted to correctness, so it
must not be read as a probability. The calibration artifact explicitly disclaims a conformal guarantee.

---

## 7. Analysis

### 7.1 The harm decomposes into a task term and a model term

The panel supports a clean separation:

> **Task term.** When a verifier cannot express "unknown", harm is 68.1–73.9% regardless of model. This is a
> property of the data and the degradation, not of the verifier. No amount of model upgrading changes it.
>
> **Model term.** Given the third label, harm spans 5.1–54.0%. The entire 1.4×–14.3× benefit is a property
> of the model.

This is actionable in a way that a single blended number would not be. It says the label space is a
*design* decision with a large, model-independent cost if you get it wrong, and that having fixed the label
space you then face a *selection* decision with an order-of-magnitude spread.

### 7.2 Under-abstention, not over-abstention

The uniformity of abstention precision (97.2–100%, all 15 models) is the most surprising result. It means
no model in the panel is meaningfully over-cautious — when they say "I cannot tell", they are right. All
observed harm comes from failing to abstain when abstention was warranted.

This inverts a common intuition about calibration work. The intervention suggested by "models are badly
calibrated" is often to sharpen decisions; here that would be exactly wrong. Any prompt, fine-tune, or
decoding change that increases decisiveness moves every model in the harmful direction. The lever that
matters is abstention *recall*.

It also explains why `gpt-5.4-nano` looks anomalous and is not. It abstains on 70% of atoms at 20%
retention, which in isolation might indicate a degenerate always-abstain policy — but its accuracy at that
retention is 94.7%, the highest in the panel, and its abstention precision is 100%. At 20% retention gold
is 69% `Not-in-KG`, so abstaining often is *correct*; nano is simply better calibrated to that, not lazier.

### 7.3 Capability does not buy calibration

Spearman −0.66 is a real association and we do not dismiss it. But the within-tier spread is roughly four
times the between-tier spread, the tier means are non-monotonic, and every vendor's internal ordering is
non-monotonic. The single best abstainer in a 15-model panel is the smallest model in its family, and it
beats that family's frontier model fourfold.

The practical reading: **an organisation cannot solve this by buying a bigger model, and cannot assume the
next model generation will solve it either.** Correct abstention under incomplete evidence appears to be a
training-recipe property that varies independently of general capability, so it must be measured per model
rather than inferred from benchmark rank.

### 7.4 On the sampling confound

Six of fifteen models ignored `temperature=0`. This is a genuine limitation of comparing vendors through a
single gateway, and we record resolved sampling per model rather than averaging it away.

It does not explain the ordering. The affected six span the panel from best (`gpt-5.4-nano`, 5.1%) to
mid-pack (`azure-o3`, 27.2%), and the worst model overall (`azure-4o-mini`, 54.0%) ran at temperature 0. A
sampling effect large enough to produce a 10× spread would have to correlate with the affected set, and it
does not. A stricter replication would fix an achievable configuration for every model or repeat each at
several temperatures; we list this as future work rather than claiming it is immaterial.

### 7.5 Why the ceiling arm is reported at all

`declared_oracle` cannot lose on CR-true. Reporting a system that cannot lose requires justification.

We report it for two reasons. First, it bounds the achievable: the gap between it and `declared_stale`
(68.3 accuracy points at 20% retention) is the value of metadata *freshness*, which is the paper's
actionable claim. Second, under the corrected gold it is no longer perfect — 99.0% accuracy, 0.919 macro-F1,
0.619 contradiction precision — so it does carry information about implementation quality even though its
safety number is definitional. We label it a ceiling everywhere it appears.

### 7.6 Design implications

1. **Give verifiers a third label.** Not optional: the alternative costs ~70% CR-true regardless of model.
2. **Measure abstention per model.** Capability rank does not predict it; the spread is 10×.
3. **Re-derive completeness metadata whenever data changes.** Stale metadata is equivalent to none.
4. **Do not infer completeness from observed density.** Occupancy is non-monotonic and threshold-fragile.
5. **Preserve identifiers end-to-end.** Retrieval recall@1 falls 88.0% → 47.0% without them.
6. **Spend engineering effort on decomposition, not on the symbolic verifier**, which is already at 100%.

---

## 8. Threats to validity

- **Gold is mechanical.** It is now independent of every system under test — the critical fix — but is
  derived from graph contents rather than human judgement. No human annotation was performed. This is the
  single largest limitation and the highest-value item to address.
- **`declared_oracle` cannot lose on the safety metric** by construction; reported as a ceiling throughout.
- **Deletion is simulated.** Clustered deletion is more realistic than uniform but remains a proxy for
  institutional data loss. No naturally incomplete graph is evaluated.
- **Oracle-selected evidence.** The panel and flat-context arms receive the exact relevant record. §6.5
  bounds how optimistic this is, but the retriever and verifier were never composed end-to-end.
- **Questions and expected triples are graph-derived**, not human-authored, so they inherit the graph's
  schema and blind spots.
- **One answer-generation run** per generator/condition; intervals do not cover LLM sampling variance.
- **Panel breadth over depth**: one seed, random mode only, four retention levels.
- **Sampling confound**: six of fifteen panel models did not honour the requested temperature (§7.4).
- **7 unscored rows** (0.04%), all `gemini-2.5-flash` JSON truncations, leaving that model at n=295–300.
- **Tier and vendor labels are editorial**, recorded in the artifact so a reader can disagree.
- **Confidence is heuristic**; calibration is descriptive, not conformal.
- **RMIT is small** (50 entities); **FactKG is binary** and moves 21.6 points with sampling method.
- **Data redistribution rights** for source catalogue records require separate review.

---

## 9. Conclusion

Missing evidence and contradicted evidence are different things, and the difference becomes expensive
exactly when a knowledge source degrades. We measured that cost under controlled deletion, against a gold
standard deliberately built to be independent of the completeness metadata any system under test consumes.

Three results stand out. A three-valued label space is **necessary** — without it, harm is 68.1–73.9%
across fifteen models from four vendors, a 5.8-point spread over a 10× capability range, so the binary
failure belongs to the task rather than the model. It is **not sufficient** — with it, harm still spans
5.1–54.0% and no model reaches zero, the best achieving 5.1% with an interval excluding zero and the median
sitting at 24.3%. And its value is **not predictable from capability** — within-tier variation is four times
between-tier variation, the ordering is non-monotonic inside every vendor, and the best abstainer in the
panel is the smallest model in its family. Underlying all of it is a single mechanism: abstention precision
is 97.2–100% everywhere, so every model's failure is under-abstention, never over-abstention.

On the systems side, completeness metadata delivers its benefit entirely through freshness. A declaration
written for a healthy catalogue and never updated is indistinguishable from having no declaration at all,
matching the metadata-free baseline to the decimal in all four pairings at every retention level, and
confidence gating does not rescue it.

We also report what this study cannot support. Our gold is mechanical rather than human-annotated; our
evidence is oracle-selected rather than retrieved; and the arm receiving perfectly synchronised metadata
cannot lose on the safety metric and is labelled a ceiling. Two claims from earlier revisions — a zero
false-contradiction rate for the proposed route, and a subsequent claim that it over-abstained — were both
artifacts of gold construction and are withdrawn here, with the invariant that broke the second now enforced
as a test.

The most valuable next step is not a larger automated sweep, which would only narrow intervals around the
same mechanically defined estimand. It is human-validated gold on a stratified sample, composition of the
measured retriever with the verifier for an end-to-end number, and repetition at several temperatures to
separate sampling from capability for the six models that ignored the requested one.

---

## Appendix A — Reproducibility

Every aggregate above derives from saved row-level JSON. Runners record input hashes, script and pipeline
hashes captured before model calls, exact arguments, model and provider identity, usage, failures, and
elapsed time.

| Evidence | Artifact |
| --- | --- |
| Gold definition | `scripts/intervention_gold.py` |
| Questions / provenance | `data/nusmods_questions_200.jsonl` + `.manifest.json`; RMIT equivalents |
| Degraded graphs | `output/experiments/nusmods_degradation_final/` (graph, `completeness.json`, `deletion_log.jsonl`, `manifest.json` per condition) |
| Symbolic routing sweep | `nusmods_rescore_intervention_gold.json` + `_analysis.json` |
| Stage attribution | `nusmods_stage_attribution_intervention_gold.json` |
| Selective risk | `nusmods_rescore_intervention_gold_calibration.json` |
| 15-model panel | `model_panel_20260803/panel_manifest.json`, `panel_analysis.json`, `flat_<model>.json` |
| Retrieval recall | `retrieval_recall_20260803/nusmods_retrieval_recall.json` |
| Oracle-context LLM baselines | `nusmods_flat_azure_intervention_gold.json`, `nusmods_flat_gemma_intervention_gold.json` |
| MiniCheck | `nusmods_minicheck_intervention_gold.json` |
| NIL linker sweep | `linker_nil.json` |
| Destruction controls | `nusmods_destruction_control.json`, `codex_destruction_control.json`, `rmit_set_destruction.summary.json` |
| Public transfer | `final_public_20260803_azure/`, `final_public_20260803_local/` |
| Machine-readable ledger | `experiments/registry.json` |

Unless prefixed with `data/`, `scripts/`, or a named run directory, paths are under
`output/experiments/incompleteness_final_20260803/`.

Regression suite: **183 tests**, including `test_no_true_fact_is_ever_labelled_contradicted` (the invariant
whose violation produced the withdrawn over-abstention claim) and `GoldIndependenceTests` (guarding against
the gold/system coupling that produced the withdrawn zero-FCR claim). Exact command sequences are in
`docs/experiment_runbook.md`.

Artifacts scored under the superseded declaration-coupled gold remain on disk for forensic comparison and
are marked non-citable in the registry. Any table reporting a flat 0.0% false-contradiction rate for a
system named plain `declared`, or a 1.000 macro-F1, originates there and is withdrawn.
