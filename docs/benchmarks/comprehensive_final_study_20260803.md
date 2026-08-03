# Comprehensive Incompleteness-Aware Verification Study

**Run date:** 2026-08-03
**Gold revision:** 2026-08-03c — declaration-independent gold, with set-relation depletion handling
**Models:** long-form arms use `azure-4.1-mini` and local `google/gemma-4-e4b`; the verifier panel
covers 15 models across OpenAI, Anthropic, Google and Meta
**Status:** automated candidate evidence; no human validation
**Primary artifact directory:** `output/experiments/incompleteness_final_20260803/`

---

## 0. What changed in this revision, and why it matters

An earlier version of this study reported that the proposed `declared` routing mode achieved a
**zero false-contradiction rate in every experimental condition**. That number was withdrawn. It was
not a measurement; it was a definition restating itself.

### The problem in plain terms

To score a system you need two things: a *prediction* and a *correct answer*. They have to come from
independent places. If the answer key is written by the same rule the student uses, the student
scores 100% and you have learned nothing about the student.

That is exactly what happened. The old gold function decided whether a missing fact should count as
`Contradicted` or `Not-in-KG` by looking up the relation in a **completeness declaration file**. The
proposed `declared` routing mode decided the same thing by looking up **the same file**. The two
pieces of code were written separately, so no line of code was shared — but the *rule* was identical.

The evidence is in the old artifact. The proposed system scored:

```
accuracy 1.000    macro-F1 1.000
Supported F1 1.000  |  Contradicted F1 1.000  |  Not-in-KG F1 1.000
bootstrap 95% CI on accuracy: [1.000, 1.000]
```

A perfect score on all three labels, in all 336 experimental cells, with a confidence interval of
zero width. Real systems do not do that. Definitions do.

The reported "binary" baseline had the same defect from the other direction. It was not a system at
all — it was one line of post-processing applied to the proposed system's output:

```python
"binary": "Contradicted" if declared_pred == "Not-in-KG" else declared_pred
```

So the headline "false-contradiction rate rises from 5.1% to 96.3%" was arithmetic. At 20% retention
the numbers were 1105 gold `Not-in-KG` cases out of 1147 predicted contradictions — and
1105 / 1147 = 0.963, the reported figure to four decimal places. That curve simply re-described how
many facts we had deleted. It would have looked identical with a random verifier plugged in.

### The fix

Three changes, all in this revision:

1. **Gold no longer reads any completeness declaration.** It is computed from two graphs only: the
   undegraded reference snapshot, and the damaged graph the system was allowed to see. See
   [`scripts/intervention_gold.py`](../../scripts/intervention_gold.py). A declaration is now purely
   a *system input* that can be correct, stale, or absent — and the score can tell those apart.
2. **`binary` is a real system.** It runs as its own pass over the graph through
   `routing_mode="binary"`, a verifier with no third label at all. It is no longer derived from
   another system's output.
3. **A new arm, `declared_stale`, was added** — the realistic case where completeness metadata was
   written for the healthy catalogue and never updated after data went missing. This is the arm that
   produces the study's most useful new finding.

### What the fix revealed

The proposed route is no longer perfect. Against the corrected gold at 20% retention it scores
**99.0% accuracy and 0.919 macro-F1** — high, but no longer the flat 1.000 that signalled
circularity. Its residual error is now visible and interpretable: it predicts 42 contradictions
where gold supports 26, giving **61.9% contradiction precision**. Those 16 extra contradictions are
all against claims that are *false in the reference world* but whose disconfirming evidence was
deleted, so they are technically unjustified under certain-answer semantics while remaining harmless
on the safety metric.

### A second correction, made during this revision

The first attempt at the new gold contained its own bug, and the finding derived from it has been
withdrawn.

Random deletion removes **individual members** of a set-valued relation and leaves the container
behind. A course whose reference prerequisite list is `[ES2002, ES2660, IS2101, LC1016]` can end up
with a condition list of just `[ES2660]`. The first implementation tested only "is the field
present?", concluded the shrunken list was authoritative, and read the absence of `ES2002` as a
*contradiction* — even though `ES2002` really is a prerequisite and is missing only because we
deleted it.

That mislabelled 230 of 296 supposed contradictions in a single experimental cell, and produced a
published claim that `declared_oracle` "recovers only 14.2% of the contradictions it should catch"
and therefore "over-abstains, discarding 85.8% of legitimately detectable contradictions". **That
claim was false.** The system was abstaining correctly; the answer key was wrong. Its actual
contradiction recall is 94.6–100% across retention levels.

The rule now applied: for a set relation, the absence of a claimed member licenses a contradiction
only when the visible member set is provably identical to the reference member set. The residual
anomaly count across all 61,164 scored rows is **5**, all from a single multi-hop prerequisite triple
(`MA4262 → MA2108S`), and all handled conservatively by falling back to `absent`.

The lesson generalises: a gold function that can label a reference-world truth as `Contradicted` is
broken, and that invariant is now a test
([`test_no_true_fact_is_ever_labelled_contradicted`](../../tests/test_intervention_gold.py)).

---

## 1. Executive verdict

The research direction is sound. The current automated evidence supports a **measurement paper**: a
controlled study of how post-hoc factuality verification degrades when the knowledge graph behind it
is incomplete. It does not support a systems paper claiming a better verifier, and it is not
journal-ready.

Four findings are carried by genuinely independent measurements — where the thing making the
prediction has no access to the thing defining the correct answer:

> **Finding A.** Across **15 models from four vendors**, giving a verifier a third label is
> *necessary but not sufficient*. Without it, every model lands at 68.1–73.9% harm regardless of
> capability — a 5.8-point spread over a 10× capability range, so the binary failure is a property of
> the task. With it, harm drops by 1.4× to 14.3× depending entirely on the model, and no model
> reaches zero: the best is 5.1% with a 95% interval of [0.8, 10.8] that excludes zero, and the panel
> median is 24.3%.

> **Finding B.** The failure mode is **uniformly under-abstention**. Abstention *precision* is
> 97.2–100% for all 15 models — when a model says "I cannot tell", it is essentially always right.
> The entire 10× spread in harm comes from abstention *recall*, 26.7% to 93.3%. Models never abstain
> when they shouldn't; they fail to abstain when they should. Any intervention that pushes models
> toward more decisions makes this strictly worse.

> **Finding C.** Completeness metadata only helps if it is *maintained*. Stale metadata performs
> **identically to having no metadata at all** on the safety measure: `declared_stale` and `binary`
> both reach 66.4% at 20% retention, matching to the decimal in all four generator/detector pairings.
> The benefit lives entirely in metadata freshness, not in the existence of a metadata field.

> **Finding D.** The symbolic verifier is not the bottleneck. Oracle linking and verification both hit
> 100%, and Stage 4 on correctly extracted atoms hits 100% for every model pairing, while end-to-end
> expected-triple F1 ranges from 98.6% down to 79.7% depending on which model reads and which model
> decomposes. The error budget is dominated by claim extraction.

A fifth result is negative and worth stating separately: **correct abstention does not track model
capability**. Spearman(competence, harm) is −0.66, so capability helps on average, but the spread
*within* the "small" tier is 48.9 points against 13.2 points between tier means, and the ordering is
non-monotonic inside every vendor. The best abstainer in the panel is the smallest model in its
family (`gpt-5.4-nano`, 5.1%), beating the frontier model (`gpt-5.5`, 20.7%) fourfold. Waiting for
better models is not a strategy.

What is **not** a contribution: atomic decomposition, graph-grounded verification, or the observation
that knowledge graphs are incomplete. All three have substantial prior art. The defensible novelty is
their junction — treating source completeness as an explicit, controllably degraded experimental
variable, and measuring asymmetric false-contradiction risk against it.

---

## 2. How gold is defined now

This section is the heart of the revision. Read it before any results table.

### 2.1 Two graphs, no metadata

Gold answers one question: *given the graph the system was actually allowed to see, what is the
correct verdict for this claim?* It uses exactly two inputs.

| Input | What it is | Role |
| --- | --- | --- |
| **Reference graph** | The full, undegraded NUSMods snapshot | Stands in for "the world". Defines what is true. |
| **Condition graph** | The damaged graph for this seed/mode/retention cell | Defines what evidence was available. |

No completeness declaration is opened at any point. That single fact is what makes every score in
this report meaningful.

### 2.2 The two things we establish per claim

For each claimed triple `(subject, relation, object)` we record two independent properties.

**`world_truth` — is the claim true in the reference world?**

| Value | Meaning |
| --- | --- |
| `true` | The reference graph asserts exactly this fact. |
| `false` | The reference graph asserts *some* value for this subject and relation, and it is a different one. The claim conflicts with reality. |
| `unknown` | The reference graph says nothing at all here. NUSMods staffing (`taughtBy`) is the deliberate example: it is naturally incomplete and is never artificially degraded, so it anchors genuine open-world absence. |

**`evidence_state` — what survived in the graph the system could see?**

| Value | Meaning |
| --- | --- |
| `confirming` | The condition graph still asserts the claimed fact. |
| `conflicting` | The condition graph asserts a different value for this subject and relation. |
| `absent` | The condition graph asserts nothing here — either our deletion removed it, or it was never there. |

### 2.3 The truth table

| `world_truth` | `evidence_state` | Gold verdict | Why |
| --- | --- | --- | --- |
| `true` | `confirming` | **Supported** | The evidence is right there. |
| `true` | `absent` | **Not-in-KG** | The claim is *true* and we deleted the proof. Calling this `Contradicted` is precisely the harm this study measures. |
| `false` | `conflicting` | **Contradicted** | The visible graph carries an incompatible value. A contradiction is justified. |
| `false` | `absent` | **Not-in-KG** | The conflicting value is gone. Nothing visible licenses a contradiction any more, even though the claim is in fact wrong. |
| `unknown` | `absent` | **Not-in-KG** | Natural open-world absence. |

The combinations `true`/`conflicting` and `unknown`/`conflicting` cannot occur, because the
degradation builder only ever *removes* facts — it never adds or edits them. The sweep counts any
such row as an anomaly. **The observed count across all 61,164 scored rows is zero**, which is an
independent confirmation that the degraded graphs really are pure deletions of the reference graph.

### 2.4 Two safety metrics, and which one to trust

The report uses two related numbers. Understanding the difference matters.

**False-contradiction rate (FCR)** — of all the contradictions a system announced, how many were
wrong? This is the traditional metric, but it depends on a *convention*: it assumes absence should be
labelled `Not-in-KG`. A reader who disagrees with that convention can dismiss it.

**Contradiction rate on true claims (CR-true)** — of all the claims that are **true in the reference
world**, how many did the system call `Contradicted`? This needs no convention about absence at all.
There is only one defensible answer to "should you contradict something that is true?", and it is no.

> **Use CR-true as the headline safety number.** It is convention-free, it is directly interpretable
> ("how often does this system call a true statement false?"), and it survives disagreement about our
> labelling choices. FCR is retained for comparability with prior work.

### 2.5 The honest caveat about `declared_oracle`

One limitation must be stated plainly rather than buried.

Under this gold, **any system that refuses to emit a contradiction from absence gets CR-true = 0 by
construction.** `declared_oracle` is such a system: it consumes a declaration regenerated for the exact
damage we applied, so every degraded relation is correctly marked incomplete and absence always routes
to `Not-in-KG`.

Therefore:

> `declared_oracle`'s zero is a **ceiling, not a result.** It answers the question "what would
> perfectly maintained completeness metadata buy you?" — nothing more. It is never presented as a win
> over the baselines.

The scientific content of this study lives in the arms that *can* emit a contradiction from absence
and that do not define gold: `declared_stale`, `binary`, `occupancy_*`, the flat-context LLM verifiers,
and MiniCheck. Those are all measured fairly.

And `declared_oracle` is no longer immune to criticism even so: §4.3 shows it loses 15.7 accuracy
points at 20% retention through massive over-abstention.

---

## 3. Experimental design

### 3.1 What the retention percentages mean

The values `100/95/90/80/50/20%` are **nominal relation-fact retention targets**.

- `100%`: no selected facts are deleted.
- `80%`: roughly 80% of the facts in each selected relation remain; roughly 20% are deleted.
- `20%`: roughly 20% remain; roughly 80% are deleted.

They are **not** accuracy, confidence, question coverage, answer sampling, or decomposition
agreement. All 11,647 NUSMods module nodes remain present in every graph — we delete *facts about*
modules, never the modules themselves.

The degraded relations are credit value, faculty/school, prerequisites, preclusions, and offered
semesters. Staffing is never degraded; it is the naturally incomplete open-world anchor.

Random deletion removes individual facts and hits its target up to integer rounding. Clustered
deletion removes whole department groups, so realized retention can differ materially by relation —
one nominal clustered 80% graph retained 82.2% of credit facts but only 68.5% of preclusion facts.
Every manifest records both requested and realized retention.

Separately, "two-pass self-consistency" means each answer is decomposed twice, at temperatures `0.1`
and `0.2`, keeping only claims that agree across both passes. It has no connection to the retention
percentage.

### 3.2 Inputs

- NUSMods: 11,647 entities; 200 questions; 300 distinct expected triples; nine question types.
- RMIT: 50 entities; 50 questions; 66 distinct expected triples; seven question types.
- NUSMods degradation: three seeds, two modes, six retention levels.
- RMIT degradation: three seeds, two modes, three retention levels.
- Public transfer: RMIT, NUSMods, FactKG, and CoDEx.

The 24 NUSMods staffing triples are open-world anchors. Expected-fact extraction metrics exclude them
because the graph asserts no staff value; open-world verification diagnostics retain them.

### 3.3 Model matrix

The NUSMods long-form study reuses identical saved answers across detector arms:

| Answer generator | Claim detector | Purpose |
| --- | --- | --- |
| Azure | Azure | Hosted self-detector |
| Gemma | Gemma | Local self-detector |
| Azure | Gemma | Detector effect on identical Azure answers |
| Gemma | Azure | Detector effect on identical Gemma answers |

Answer temperature is `0.2`; decomposition uses `0.1` and `0.2`. Cross-model rows hold answer text
fixed, but decomposition remains stochastic, so these are informative contrasts rather than
deterministic paired causal estimates.

### 3.4 Systems under test

| System | Completeness metadata it receives | Can it contradict from absence? | Role |
| --- | --- | --- | --- |
| `declared_oracle` | Declaration regenerated for this exact damage | No | **Ceiling.** What perfect metadata buys. |
| `declared_stale` | Declaration for the *healthy* snapshot, never updated | Yes | **The realistic case.** Carries the key finding. |
| `binary` | None, and no third label at all | Yes | **Floor.** Models an external binary fact checker. |
| `occupancy_<t>` | Inferred from observed relation density at threshold `t` | Yes | Heuristic substitute for metadata. |
| Flat-context LLM | Natural-language tri-state instruction + oracle-selected records | Yes | Independent predictor. |
| MiniCheck | None; binary Supported/Unsupported | Yes (by mapping) | Independent predictor; label-space probe. |

All six are scored against the same declaration-independent gold. Only `declared_oracle` is structurally
incapable of a false contradiction, and it is labelled a ceiling everywhere it appears.

### 3.5 Statistics

Incompleteness intervals use 1,000 bootstrap samples clustered by `(deletion seed, question_id)`.
Rates with zero predicted decisions are `null`, never zero. Paired system differences are computed on
identical atoms. Calibration uses a question-grouped 50/50 split and binomial upper bounds; it is a
diagnostic, not conformal risk control.

---

## 4. Results

### 4.1 Deterministic ceilings and controls

| Control | Result |
| --- | ---: |
| Gold expected triples → verifier | 100.0% |
| Gold expected triples → linker → verifier | 100.0% |
| Stage 4 on Azure-extracted atoms | 100.0% |
| Stage 4 on final Gemma-extracted atoms | 100.0% |
| Gold anomalies across 61,164 scored rows | 5 (one multi-hop triple) |
| NUSMods shuffled-graph prediction change | 34.76% (PASS, gate 20%) |
| CoDEx shuffled-graph prediction change | 29.53% (PASS) |
| RMIT set control: shuffle accuracy drop | 42.4 points |
| RMIT set control: empty-graph drop | 51.5 points |

The oracle ceilings survive the gold change, and that now means something it did not mean before:
because gold no longer consults the declaration, a 100% oracle ceiling is evidence that the
researcher's completeness declaration is **empirically consistent with the snapshot** across all 300
expected triples. Under the old gold this was circular.

The anomaly counter is a self-check on the gold function itself: it counts rows where a claim true in
the reference world was nevertheless read as conflicting with the condition graph, which pure deletion
cannot produce. It sat at 230+ per cell before the set-relation fix in §0 and is now 5 across the
whole study — all five from the single multi-hop triple `MA4262 → MA2108S`, where the reference
prerequisite is reachable only through an intermediate course. Those rows fall back to `absent`, the
conservative label.

### 4.2 Headline: contradiction rate on true claims

Pooled across three seeds and all three answer-generation conditions, random deletion. Every number
is the fraction of **claims true in the reference world** that the system called `Contradicted`.
Lower is safer.

| Generator → detector | System | 100% | 80% | 50% | 20% |
| --- | --- | ---: | ---: | ---: | ---: |
| Azure → Azure | `binary` | 0.0% | 15.4% | 39.3% | **66.4%** |
| Azure → Azure | `declared_stale` | 0.0% | 15.4% | 39.3% | **66.4%** |
| Azure → Azure | `declared_oracle` *(ceiling)* | 0.0% | 0.0% | 0.0% | 0.0% |
| Azure → Gemma | `binary` | 0.0% | 17.2% | 42.1% | 70.5% |
| Azure → Gemma | `declared_stale` | 0.0% | 17.2% | 42.1% | 70.5% |
| Gemma → Azure | `binary` | 0.0% | 15.8% | 41.6% | 73.9% |
| Gemma → Azure | `declared_stale` | 0.0% | 15.8% | 41.6% | 73.9% |
| Gemma → Gemma | `binary` | 0.0% | 17.3% | 43.7% | 76.1% |
| Gemma → Gemma | `declared_stale` | 0.0% | 17.3% | 43.7% | 76.1% |

Azure self-detection at 20% retention: 66.4% with a question/seed-clustered 95% interval of
`[62.8, 70.1]` over 1,374 true-world claims. The endpoint change is far beyond sampling uncertainty.

**The `declared_stale` row equals the `binary` row exactly, in all four pairings, at every retention
level.** This is the study's most useful new result, and it is not a coincidence — it is mechanically
explicable. When a relation is declared complete but its facts have been deleted, closed-world
routing forces `Contradicted`, which is precisely what a system with no metadata does. The two arms
can only diverge on relations that were *already* declared incomplete in the healthy snapshot
(staffing) and on unresolvable entities, and those are a small minority of true-world claims.

The practical reading is blunt:

> Shipping a completeness-metadata field buys you **nothing** if the metadata is not re-derived
> whenever the underlying data changes. An organisation that adds declarations and then lets them go
> stale has the safety profile of an organisation with no declarations at all.

Note also that at 100% retention every system scores 0.0% on this metric. Under the old FCR-based
headline the same cells read 5.1%–62.5%, which invited the misreading that the systems were already
unsafe on intact data. They were not: those apparent errors were contradictions against naturally
missing staffing facts and unresolved claims, not against true claims. The convention-free metric
makes the distinction visible.

Clustered deletion reproduces the pattern. Azure self-detection: 0.0% → 15.9% → 45.1% → 69.4%.

### 4.3 The cost of the safe route

`declared_oracle` is safe. The corrected gold shows the cost is **coverage, not correctness** — and
specifically *not* the over-abstention this section previously reported.

Azure self-detection, random 20% retention:

| Metric | Value |
| --- | ---: |
| Accuracy | 99.0% |
| Macro-F1 | 0.919 |
| `Supported` precision / recall / F1 | 1.000 / 1.000 / 1.000 |
| `Contradicted` precision / recall / F1 | **0.619** / 1.000 / 0.765 |
| `Not-in-KG` precision / recall / F1 | 1.000 / 0.986 / 0.993 |
| Decision coverage | 31.7% |

The route catches **every** contradiction gold supports (recall 1.000). Its residual error runs the
other way: it predicts 42 contradictions where gold supports 26. Those 16 extra cases are claims that
are genuinely false in the reference world, but whose disconfirming evidence was deleted, so the
visible graph no longer justifies the verdict. They are unjustified-but-not-harmful — the
contradiction rate on *true* claims stays at 0.0%.

The real price is coverage. Across 100/80/50/20% retention, `declared_oracle` decision coverage falls
99.3% → 82.5% → 57.5% → 31.7%, while `declared_stale` holds 99.3% and `binary` holds 100%. **The safe
system buys its safety by answering roughly a third as often at severe incompleteness.** That is the
honest trade-off: fewer answers, but no false certainty.

Whether relation-level granularity is coarse enough to matter remains an open question — but this
experiment does not demonstrate that it is. The earlier claim that it discarded 85.8% of detectable
contradictions was an artifact of the set-relation gold bug described in §0 and is withdrawn.

### 4.4 Occupancy is an unreliable substitute

Inferring completeness from observed relation density is attractive because it needs no metadata. It
does not work. Azure self-detection, random deletion, contradiction rate on true claims:

| Threshold | 100% | 95% | 90% | 80% | 50% | 20% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 | 0.0% | 2.5% | 4.0% | 7.9% | **20.5%** | **0.0%** |
| 0.70 | 0.0% | 2.5% | 4.0% | 7.9% | 0.0% | 0.0% |
| 0.85 | 0.0% | 2.5% | 4.0% | 0.0% | 0.0% | 0.0% |
| 0.95 | 0.0% | 2.5% | 0.0% | 0.0% | 0.0% | 0.0% |

The 0.50 row is the clearest illustration: harm rises steadily to 20.5% at 50% retention, then drops
to zero at 20% retention. Nothing improved. The relation simply became sparse enough to cross the
threshold, flipping the whole relation from "closed" to "open" in one step.

This non-monotonicity is the core objection to occupancy. The metric is a property of the *damaged*
graph, so the more damage there is, the more likely the heuristic is to accidentally do the right
thing — and where the threshold sits determines the entire behaviour. Each threshold flips at a
different retention level (0.95 flips at 90%, 0.50 at 20%), so there is no safe default.

### 4.5 External verifier baselines — the independent evidence

These are the arms where the predictor has no connection whatsoever to the gold definition. They
carry the most weight.

#### Azure with oracle-selected evidence

The model receives the exact graph records relevant to the claim and is instructed that it may answer
`Not-in-KG`. This is a generous setting — a deployed retriever would do worse.

| Mode | Retention | Tri-state accuracy | **CR-true** | Binary-collapse accuracy | **Binary CR-true** | False-support rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 100% | 92.0% | **0.0%** | 92.0% | 0.0% | 8.0% |
| Random | 80% | 83.3% | **7.6%** | 77.7% | 14.1% | 10.7% |
| Random | 50% | 72.7% | **18.8%** | 51.3% | 42.0% | 16.3% |
| Random | 20% | 64.3% | **25.4%** | 24.7% | 68.5% | 33.3% |
| Clustered | 20% | 80.7% | **9.8%** | 23.0% | 72.5% | 31.0% |

Zero call failures in 2,700 unique classifications.

Two things are true at once, and both matter:

1. **Tri-state prompting genuinely helps.** At 20% retention it cuts the contradiction rate on true
   claims from 68.5% to 25.4% — a 2.7× reduction — and holds accuracy at 64.3% where the binary
   collapse falls to 24.7%. Giving the model an "unknown" option is worth real money.
2. **It is not sufficient.** One in four true claims still gets contradicted. A natural-language
   instruction to say "unknown" is a soft preference the model trades off against other pressures;
   it is not the deterministic semantic control that explicit metadata provides. The rising
   false-support rate (8.0% → 33.3%) shows the failure is not simply excess caution — the model gets
   worse in both directions as its evidence thins.

Gemma under the identical protocol is markedly weaker:

| Mode | Retention | Tri-state accuracy | **CR-true** | Binary-collapse accuracy | **Binary CR-true** | False-support rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 100% | 87.3% | 10.9% | 79.3% | 13.8% | 0.0% |
| Random | 80% | 74.0% | 22.8% | 65.0% | 27.9% | 2.0% |
| Random | 50% | 55.0% | 44.6% | 43.0% | 51.8% | 3.0% |
| Random | 20% | 36.7% | 67.0% | 21.7% | 75.7% | 3.0% |
| Clustered | 20% | 46.0% | 58.3% | 21.3% | 76.8% | 0.0% |

All 2,700 Gemma classifications produced a final prediction with no terminal call errors. Note that
Gemma already contradicts 10.9% of true claims on a *fully intact* graph, and that tri-state
prompting buys it far less than it buys Azure (67.0% vs 75.7% at 20% retention — a 1.13× reduction,
against Azure's 2.7×). **The ability to use an "unknown" option is itself a model-capability
question**, not something that comes free with the prompt.

#### MiniCheck

MiniCheck completed 2,700 unique inferences on CPU. Its native binary accuracy actually *rises* as
facts are deleted, from 71.3% at full retention to 83.3% at random 20%, because missing-evidence
documents become easy to call `Unsupported`.

But a binary checker has no way to distinguish "the graph disagrees" from "the graph is silent".
Mapping `Unsupported` to `Contradicted` gives (tri-state accuracy falls 71.3% → 17.0%):

| Mode | Retention | Tri-state accuracy | **CR-true** | False-support rate |
| --- | ---: | ---: | ---: | ---: |
| Random | 100% | 71.3% | 22.5% | 10.1% |
| Random | 80% | 61.3% | 33.0% | 12.0% |
| Random | 50% | 40.0% | 55.1% | 18.9% |
| Random | 20% | 17.0% | **80.8%** | 33.8% |
| Clustered | 20% | 13.7% | **85.1%** | 36.9% |

This inversion — the metric the checker optimises improves precisely as the checker becomes more
dangerous — is a clean argument that **label space, not model quality, is the binding constraint**.
MiniCheck is not bad at its intended job. Its intended job is the wrong shape for open-world
verification.

### 4.6 The 15-model panel: is correct abstention a capability, a quirk, or a floor?

Findings A and D above rested on two models, which cannot distinguish three very different
explanations for why a tri-state prompt helps unequally. This section runs the identical protocol —
same claims, same oracle-selected evidence, same prompt, same declaration-independent gold — across
**15 models spanning four vendors and a nano-to-frontier capability range**. Only the model varies.

The three hypotheses, and what would confirm each:

1. **Capability scaling** — stronger models abstain correctly, so the problem solves itself as models
   improve. Confirmed by a strongly negative competence/harm correlation *and* the best models
   approaching zero.
2. **Idiosyncrasy** — abstention is a training-recipe quirk, largely independent of capability.
   Confirmed if within-tier spread swamps between-tier spread.
3. **A structural floor** — every model retains substantial harm under severe incompleteness.
   Confirmed if even the best model stays well above zero.

Of 18,000 classifications, **17,993 produced a prediction**. The 7 failures (0.04%) are all
`gemini-2.5-flash` responses whose JSON was truncated mid-token, affecting 5 unique triples and
leaving that model's cells at n=295–300 rather than 300. Failed rows are excluded from scoring and
never replaced with a default label. The cause — a thinking trace consuming the output budget — is
the same one that initially broke `gemini-2.5-pro`; the token-budget rule now covers the whole
Gemini 2.5 family, so a rerun would not hit it.

#### Results at random 20% retention

Sorted by the convention-free safety metric. `absP`/`absR` are abstention precision and recall — of
the model's `Not-in-KG` answers, how many were warranted, and of the claims the graph genuinely
cannot settle, how many did it abstain on.

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

#### Finding 1: the failure mode is *uniformly* under-abstention

**Abstention precision is 97.2–100% for every one of the 15 models.** When a model says "I cannot
tell from this evidence", it is essentially always right to. Not one model in the panel is
over-cautious.

The entire 10× spread in harm is driven by abstention *recall*, which ranges from 26.7% to 93.3%.
Models fail by **not abstaining when they should**, never by abstaining when they shouldn't.

This matters for what to do about it. The problem is not that models are too timid and need
encouragement to commit; it is that they commit when the evidence does not support commitment. An
intervention that pushes models toward more decisions makes this strictly worse.

#### Finding 2: binary-collapse harm is a constant of the task, not of the model

Across all 15 models the binary-collapse contradiction rate on true claims sits between **68.1% and
73.9%** — a 5.8-point spread over a capability range spanning `azure-4o-mini` to `gpt-5.5` and
`claude-opus-4-7`.

This is the cleanest decomposition the study produces:

> **When a verifier cannot express "unknown", the harm is a property of the task and the data, and
> model choice is nearly irrelevant. The entire benefit of a third label — a 1.4× to 14.3× reduction
> — is a property of the model.**

No amount of model upgrading rescues a binary label space. Conversely, giving a model the third label
is necessary but wildly variable in how much it delivers.

#### Finding 3: capability predicts harm weakly; idiosyncrasy dominates

Spearman correlation between full-retention competence and 20%-retention harm is **−0.66**, and
between competence and abstention benefit **+0.69**. So capability does help on average.

But it is a weak predictor next to within-tier variation:

| Grouping | Mean harm | Range within group |
| --- | ---: | ---: |
| **By tier** — frontier | 19.4% | 2.6 pts (n=2) |
| large | 20.5% | 26.5 pts |
| reasoning | 27.2% | — (n=1) |
| small | 29.0% | **48.9 pts** |
| mid | 31.6% | 25.2 pts |
| open-weights | 32.6% | — (n=1) |
| **By vendor** — OpenAI | 21.7% | 48.9 pts |
| Anthropic | 27.3% | 21.4 pts |
| Meta | 32.6% | — (n=1) |
| Google | 38.1% | 11.4 pts |

The spread *between* tier means is 13.2 points. The spread *within* the "small" tier alone is 48.9
points — nearly four times larger. The tier ordering is also non-monotonic: mid-tier models average
worse than small-tier ones.

The same non-monotonicity appears **inside every vendor**:

- OpenAI: `gpt-5.4-nano` (small) at 5.1% beats `gpt-5.5` (frontier) at 20.7% — 4× better from the
  smallest model in the family — while `azure-4o-mini` (also small) is worst in the entire panel at
  54.0%.
- Anthropic: `claude-opus-4-7` 18.1% < `claude-haiku-4-5` 24.3% < `claude-sonnet-4-6` 39.5%. The
  mid-tier model is the weakest, not the smallest.
- Google: `gemini-2.5-flash-lite` (small) 32.6% < `gemini-2.5-pro` (large) 37.7% < `gemini-2.5-flash`
  (mid) 44.0%. Again the smallest is best.

If correct abstention were a capability that scales, these orderings would not look like this.

#### Finding 4: there is a floor, and it is not zero

The best model in the panel reaches 5.1%, with a 95% interval of **[0.8, 10.8] that excludes zero**.
The panel median is 24.3%. Fourteen of fifteen models exceed 11%.

So even under conditions deliberately generous to the model — oracle-selected evidence, an explicit
tri-state instruction, temperature 0 where the provider allows it — **a verifier reading a degraded
graph contradicts true statements at a rate no current model drives to zero.** That is the empirical
case for handling completeness explicitly in the system rather than hoping the model handles it.

#### What this means for the study's framing

The two-model version of Finding A said "tri-state prompting helps, and the benefit is
model-dependent". The panel sharpens it considerably:

> Tri-state prompting is **necessary** — without it, every model lands at 68–74% harm regardless of
> capability. It is **not sufficient** — no model reaches zero, and the median remains at 24.3%.
> And the amount it delivers is **not predictable from model capability** — the best abstainer in the
> panel is the smallest model in its family, and within-tier variation is four times larger than
> between-tier variation.

#### Confound: not every model honoured temperature 0

Six of the fifteen — `azure-o3`, `claude-opus-4-7`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`,
`gpt-5.5` — reject `temperature=0` and ran at their provider default. Part of any difference between
those and the temperature-0 models is sampling rather than capability.

This does not explain the ordering: the affected six span the panel from best (`gpt-5.4-nano`, 5.1%)
to mid-pack (`azure-o3`, 27.2%), and the worst model overall (`azure-4o-mini`, 54.0%) ran at
temperature 0. But it is a real limitation of cross-vendor comparison through a single gateway, it is
recorded per-model under `run.sampling`, and a stricter replication would need to fix an achievable
sampling configuration for every model or repeat each at several temperatures.

Artifacts: `output/experiments/model_panel_20260803/`, produced by
[`scripts/run_model_panel.py`](../../scripts/run_model_panel.py) and analysed by
[`scripts/analyze_model_panel.py`](../../scripts/analyze_model_panel.py).

### 4.7 Stage-wise end-to-end attribution

Expected-triple F1 on full-context answers (unchanged by the gold revision, since these metrics
concern extraction rather than absence routing):

| Generator → detector | Extraction coverage | Expected-triple F1 | Exact expected set | Stage 4 on extracted atoms |
| --- | ---: | ---: | ---: | ---: |
| Azure → Azure | 87.5% | 98.6% | 96.6% | 100.0% |
| Azure → Gemma | 80.0% | 91.1% | 79.0% | 100.0% |
| Gemma → Azure | 76.5% | 87.4% | 77.8% | 100.0% |
| Gemma → Gemma | 70.0% | 79.7% | 65.3% | 100.0% |

Azure self-detection changes strongly with evidence: expected-triple F1 is 23.2% closed-book, 63.0%
with degraded context, and 98.6% with full context.

The cross-detector arms separate the two model roles cleanly. On identical Gemma answers, swapping
the detector from Gemma to Azure raises full-context F1 by 7.7 points. On identical Azure answers,
swapping Azure for Gemma lowers it by 7.5 points. Holding the detector fixed, Azure answers beat
Gemma answers by 11.2–11.4 points. **Both stages matter, and answer content matters more**, but
decomposition adds a second, separately measurable loss.

Because Stage 4 is at 100% in every pairing, the practical conclusion is that effort spent improving
the symbolic verifier is wasted; effort spent on decomposition and linking is not.

### 4.8 How generous is the oracle-context assumption?

Every flat-context result above hands the verifier the exact record it needs, selected from the known
expected triple. In retrieval terms that is **recall@1 = 100% with perfect relation selection**. This
section measures what a real retriever achieves on the same questions, so the size of that assumption
is a number rather than a caveat.

The retriever is Okapi BM25 over all 11,647 module records (code, title, school, department, and
description), with stopword removal, exact course-code promotion, and an optional
`all-MiniLM-L6-v2` dense rerank of the top 50 candidates. Exact-identifier promotion matters: any real
catalogue search treats a course code as a near-certain intent signal, and a retriever that ignores
identifiers would understate a competent deployment.

Two query modes are reported, because they behave completely differently:

| Query mode | k=1 | k=3 | k=5 | k=10 | k=20 | k=50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Code-bearing** (question as generated) | **88.0%** | 97.5% | 98.0% | 98.0% | 100.0% | 100.0% |
| **Title-only** (code replaced by course title) | **47.0%** | 68.0% | 76.0% | 85.5% | 93.0% | 98.5% |

Reading, against the oracle assumption of 100% at k=1:

- **With an identifier present, oracle context overstates retrieval by about 12 points at rank 1**
  and about 2 points by rank 10. The residual failures are multi-code questions
  (prerequisite/preclusion existence) where two codes are promoted and the target is second.
- **Without an identifier, it overstates by 53 points at rank 1** and 14.5 points at rank 10. Course
  titles are frequently generic or duplicated, so lexical and dense matching both plateau.
- The dense rerank does **not** help (86.5% vs 88.0% code, 44.0% vs 47.0% title-only at k=1). On
  short catalogue records with a heavy identifier signal, a general-purpose sentence embedding adds
  nothing over tuned BM25. Reported as a negative result rather than dropped.

This corroborates the NIL finding in §4.9 from an independent direction and sharpens the deployment
recommendation: **preserve identifiers end-to-end**. Where identifiers survive, the oracle-context
numbers are close to achievable; where only titles survive, they are optimistic by a wide margin and
every downstream verification number should be discounted accordingly.

Artifact: `output/experiments/retrieval_recall_20260803/nusmods_retrieval_recall.json`, produced by
[`scripts/evaluate_retrieval_recall.py`](../../scripts/evaluate_retrieval_recall.py). No model calls.

### 4.9 NIL entity linking

The 1,000-example title-only held-out stress test contains 500 active and 500 held-out entities. At
the deployed 0.95 threshold:

- total exact/NIL link accuracy: 57.2%
- In-KB precision / recall / F1: 68.5% / 37.4% / 48.4%
- NIL precision / recall / F1: 62.9% / 77.0% / 69.2%
- accepted-link coverage: 38.8%

At 0.99 total accuracy is only 58.2%. Ambiguous title-only mentions impose a hard ceiling: duplicate
or generic course titles cannot prove a mention belongs to an active rather than held-out entity.
Course-code linking is perfect in the oracle attribution arm, so a realistic deployment should
preserve identifiers or add a context-aware linker.

### 4.10 Confidence and selective risk

On the held-out test split for Azure self-detection, with a 5% diagnostic false-contradiction target:

| System | Threshold selected | Contradiction decisions accepted | Decision coverage | Observed risk | Binomial upper bound | ECE (all rows) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `binary` | 1.000 | 138 / 3,419 | 4.0% | 0.0% | 2.15% | 0.058 |
| `declared_stale` | 1.000 | 138 / 3,311 | 4.2% | 0.0% | 2.15% | 0.064 |
| `occupancy_0.85` | 1.000 | 138 / 934 | 14.8% | 0.0% | 2.15% | 0.091 |
| `declared_oracle` *(ceiling)* | 0.299 | 736 / 858 | 85.8% | 0.0% | 0.41% | 0.109 |

`declared_stale` again tracks `binary` almost exactly: both must throw away roughly 96% of their
contradiction decisions to reach the risk target, whereas `declared_oracle` keeps 85.8% of its own.
Confidence gating cannot rescue stale metadata.

Note the ECE column runs the *opposite* direction to accuracy: the most accurate system has the worst
calibration error. That is not a paradox — the confidence formula is heuristic and is not fitted to
correctness, so a system that is right nearly always still reports middling confidence. **Confidence
in this pipeline should not be read as a probability**, and the calibration artifact explicitly
disclaims a conformal guarantee.

### 4.11 RMIT and public transfer

Hosted final public results (random sampling where applicable):

| Dataset | Azure accuracy | Macro-F1 | Notes |
| --- | ---: | ---: | --- |
| RMIT, 300 rows | 97.0% | 98.2% | Institutional synthetic claim transfer |
| NUSMods, 500 rows | 99.8% | 99.8% | Tri-state catalog benchmark |
| CoDEx, 500 rows | 84.8% | 84.5% | Open-domain tri-state |
| FactKG, 500 rows | 60.4% | 50.2% | Binary labels; random sample |

Local final results:

| Dataset | Gemma accuracy | Macro-F1 | Notes |
| --- | ---: | ---: | --- |
| RMIT, 300 rows | 75.0% | 80.3% | 88.0% decision coverage; 85.2% selective accuracy |
| NUSMods, 500 rows | 99.4% | 99.4% | Same under prefix and random sampling |
| CoDEx, 500 rows | 79.8% | 79.7% | Prefix accuracy is 77.0% |
| FactKG, 500 rows | 59.0% | 47.4% | Prefix accuracy is 82.4%; random is the headline |

All cells exit with zero harness failures and start-time code hashes in the process manifest.

**FactKG exposes a methodological trap worth reporting on its own.** Prefix sampling gives Azure
82.0%; random sampling gives 60.4%. The 21.6-point gap is entirely sampling composition — FactKG is
ordered by reasoning type, so a prefix covers only two ordered blocks and carries a 64.6% majority
floor. The local run independently reproduces this with a 23.4-point gap. Prefix results are retained
only as a bias diagnostic. Anyone benchmarking on FactKG should sample randomly and say so.

RMIT repeats the main pattern on a smaller graph: full-context expected-triple F1 is 78.8% for Azure
(100% extraction coverage, 72% exact sets) and 67.8% for Gemma (80% coverage, 52% exact sets), with
Stage 4 and both oracle stages at 100%.

---

## 5. Relation to prior work and the novelty boundary

Atomic claim decomposition and retrieval-grounded factuality are established by
[FActScore](https://aclanthology.org/2023.emnlp-main.741/),
[SAFE](https://arxiv.org/abs/2403.18802),
[RefChecker](https://aclanthology.org/2024.emnlp-main.395/), and
[VeriScore](https://aclanthology.org/2024.findings-emnlp.552/). Efficient binary evidence checking is
the goal of [MiniCheck](https://aclanthology.org/2024.emnlp-main.499/). Fact verification over
knowledge graphs is studied by [FactKG](https://aclanthology.org/2023.acl-long.895/).

Knowledge-base completeness statements and partial closed-world reasoning predate this work
([Darari et al. 2014](https://arxiv.org/abs/1408.6395),
[fine-grained completeness statements](https://arxiv.org/abs/1604.08377)), and a modern
[survey](https://arxiv.org/abs/2305.05403) covers KG completeness and recall. Recent work on KG-RAG
incompleteness and incomplete-KG completion means "KGs are incomplete" cannot be claimed as novel
([KG-RAG study](https://arxiv.org/abs/2504.05163),
[MusKGC](https://aclanthology.org/2025.emnlp-main.508/)).

The narrower defensible gap: long-form post-hoc factuality work rarely treats source completeness as
**explicit metadata whose controlled degradation is evaluated through asymmetric false-contradiction
risk**, and rarely distinguishes fresh metadata from stale metadata as an experimental variable. A
literature review must phrase this as a gap supported by the reviewed sources, not as proof that no
prior paper exists.

---

## 6. Publication assessment

### What can be claimed now

- Controlled relation-fact deletion makes completeness dependence measurable, with a
  convention-free safety metric.
- Across 15 models and four vendors, a tri-state label space is necessary but not sufficient:
  binary-collapse harm is 68.1–73.9% regardless of model, while tri-state harm spans 5.1–54.0% and
  no model reaches zero (best 5.1%, CI [0.8, 10.8]; median 24.3%).
- The failure mode is uniformly under-abstention: abstention precision is 97.2–100% for every model,
  and all variation is in abstention recall (26.7–93.3%).
- Correct abstention does not track capability: within-tier spread (48.9 points) is roughly four
  times the between-tier spread (13.2 points), and the ordering is non-monotonic inside every vendor.
- Retrieval recall bounds how optimistic the oracle-context arm is: 88.0% at rank 1 with identifiers
  present, 47.0% without, against an assumed 100%.
- Stale completeness metadata is statistically indistinguishable from no metadata on the safety
  metric.
- Occupancy inference is non-monotonic and threshold-fragile.
- Binary external fact checkers have a label-space defect, evidenced by accuracy rising while
  safety collapses.
- Correctly maintained relation-level declarations keep full contradiction recall under deletion,
  and pay for their safety in coverage (99.3% → 31.7%) rather than in missed contradictions.
- Stage attribution identifies decomposition, not symbolic lookup, as the end-to-end bottleneck.

### What cannot be claimed now

- Independently validated real-world factuality accuracy — gold is still mechanically derived from
  graph contents, with no human annotation.
- Journal-level superiority over established factuality systems.
- Realistic retrieval performance — the context arms use oracle subject/relation selection.
- Institution-authorised correctness of the completeness declarations.
- Conformal or calibrated deployment safety.
- Broad generalisation beyond catalogue schemas and the two public benchmarks.

### Venue judgment

| Target | Readiness | Reason |
| --- | --- | --- |
| Master's thesis | **Yes, now** | Methodology, implementation, controls, and both positive and negative findings form a coherent thesis with an honest validity boundary. |
| Workshop / short paper | **Yes, now** | The gold fix removed the blocking defect. Findings A–C are independent measurements with clustered intervals. |
| Full conference paper | **Reachable** | Needs human-validated gold on a stratified sample plus a real retriever. Roughly 6–8 weeks of work; see §8. |
| Journal | **No** | Requires everything above plus natural incompleteness and repeated stochastic runs. |

---

## 7. Threats to validity

- **Gold is mechanical.** It is now independent of the systems under test, which was the critical
  fix, but it is still derived from graph contents rather than human judgement. A human study is
  the single highest-value remaining item.
- **`declared_oracle` cannot lose on the safety metric** by construction, and is reported as a
  ceiling throughout. Do not read its zero as an empirical result.
- **Deletion is simulated.** Clustered deletion is more realistic than uniform deletion but is still
  a proxy for institutional data loss.
- **Questions and expected triples are graph-derived**, not human-authored.
- **One answer-generation run per generator/condition** does not estimate LLM sampling variance.
- **Cross-detector decompositions remain stochastic** even with identical answer text.
- **The flat-context baseline receives oracle-selected context**, so its numbers are an upper bound
  on what a retrieval-based deployment would achieve.
- **The local Gemma model often omits or mis-types atoms**; two-pass agreement trades recall for
  precision.
- **The NIL test uses deliberately hard title-only mentions** and does not represent code-rich
  administrative queries.
- **RMIT has only 50 entities and 50 questions.**
- **FactKG is binary and ordered by reasoning type**; sampling method changes the apparent result by
  over 20 points.
- **Confidence is heuristic** and the calibration diagnostic is not a guarantee.
- **Data redistribution rights** for source catalogue records require a separate release review.

---

## 8. Recommended next steps, in priority order

The single highest-value remaining item is **not** another model sweep. Adding automated rows now
only narrows the interval around the same mechanically defined estimand.

**P1 — Human-validated gold on a stratified sample.** 300 claims, stratified across Supported /
Contradicted / deleted-absent / naturally-absent, two annotators, report Cohen's κ. This converts
every "mechanical gold" caveat into "gold validated at κ = 0.8x on a stratified sample" and is what
makes Finding A unassailable. Estimated effort: one weekend.

**P1 — Replace oracle context with a real retriever.** BM25 over module records plus an embedding
rerank; report retrieval recall separately from verification accuracy. Roughly a day's work, and it
removes the asterisk currently attached to every flat-context number.

**P2 — Three or more answer-generation runs** per generator/condition, so the intervals cover LLM
sampling variance and not only deletion-seed and question variance. This also addresses the panel's
sampling confound: six of the fifteen models reject `temperature=0` and ran at a provider default,
so repeating each at several temperatures would separate sampling from capability.

**P2 — Test finer-grained completeness declarations.** §4.3 shows relation-level flags cost coverage
(99.3% → 31.7% at 20% retention) without costing contradiction recall. Whether fact-level or
entity-level declarations recover that coverage is a concrete, testable question this study leaves
open — it is no longer a demonstrated defect, only an untested hypothesis.

**P2 — A naturally incomplete graph.** A time-sliced NUSMods snapshot pair (for example AY2023 vs
AY2024) provides real, non-simulated missingness from already-cached data, and would show whether the
simulated-deletion curve predicts behaviour on genuine absence.

**P3 — Scale the question set.** 200 questions and 300 triples is adequate for a thesis and thin for
a conference. The generator is deterministic, so 1,000 questions costs compute rather than design.
Do this last.

---

## 9. Reproducibility and authoritative artifacts

| Evidence | Authoritative artifact |
| --- | --- |
| Declaration-independent gold definition | `scripts/intervention_gold.py` |
| NUSMods questions / provenance | `data/nusmods_questions_200.jsonl`, `data/nusmods_questions_200.manifest.json` |
| RMIT questions / provenance | `data/rmit_questions_50.jsonl`, `data/rmit_questions_50.manifest.json` |
| NUSMods multi-model deletion rescore | `nusmods_rescore_intervention_gold.json` and `_analysis.json` |
| NUSMods stage attribution | `nusmods_stage_attribution_intervention_gold.json` |
| NUSMods calibration diagnostic | `nusmods_rescore_intervention_gold_calibration.json` |
| Model-free ceilings | `nusmods_oracle_sweep_final.json`, `rmit_oracle_sweep_final.json` |
| Azure / Gemma oracle-context baselines | `nusmods_flat_azure_intervention_gold.json`, `nusmods_flat_gemma_intervention_gold.json` |
| MiniCheck baseline | `nusmods_minicheck_intervention_gold.json` |
| 15-model verifier panel | `model_panel_20260803/panel_manifest.json`, `panel_analysis.json`, `flat_<model>.json` |
| Retrieval recall bound | `retrieval_recall_20260803/nusmods_retrieval_recall.json` |
| NIL linker sweep | `linker_nil.json` |
| Destruction controls | `nusmods_destruction_control.json`, `codex_destruction_control.json`, `rmit_set_destruction.summary.json` |
| RMIT long-form transfer | `rmit_rescore_authoritative.json`, `rmit_stage_attribution_authoritative.json` |
| Hosted public transfer | `final_public_20260803_azure/aggregate_summary.json`, `process_manifest.json` |
| Local public transfer | `final_public_20260803_local/aggregate_summary.json`, `process_manifest.json` |
| Regression evidence | `tests/` — **183 tests passing** |

Unless a path begins with `data/`, `scripts/`, `tests/` or a public run directory, entries are under
`output/experiments/incompleteness_final_20260803/`.

Every reported aggregate is derived from saved row-level JSON. The external-baseline artifacts retain
the previous declaration-coupled label under `gold_previous_declaration_coupled` alongside the new
one, so the effect of the gold revision is auditable row by row (130 of 3,000 rows changed).

The superseded declaration-coupled artifacts — `nusmods_rescore_authoritative.json` and its analysis,
calibration, and stage-attribution companions — are retained on disk for forensic comparison but are
**not current evidence**. Any table reporting a flat 0.0% false-contradiction rate for a system named
plain `declared`, or a 1.000 macro-F1, comes from those files and has been withdrawn.
