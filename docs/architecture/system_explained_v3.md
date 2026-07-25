# The System, Explained Simply

*A plain-language walkthrough of what the verifier actually does.* For the precise version see
[`methodology.md`](methodology.md); for code-level detail see [`system_expert_review.md`](system_expert_review.md).

> Earlier versions of this file described two components — an automatic completeness estimator and a
> calibrated abstainer — as if they were built. They are not. They remain the plan, in
> [`design.md`](design.md). This file now describes only the working system.

---

## 1. The idea, in one analogy

Imagine a **fact-checker with a filing cabinet**. Someone hands them a written statement about
university courses. Their job is to check it against the official records and mark each factual claim
as backed up, contradicted, or unconfirmable.

Three things make this harder than it sounds, and they shape the whole design:

1. **A statement isn't one fact.** "CS201 is worth 12 credits and is taught by Dr Lee" is two claims
   that can have different answers. So the first job is chopping the statement into checkable pieces.
2. **The words don't match the filing system.** The statement says "Dr Lee"; the cabinet has a
   coordinator field with "Lee, Jonathan". The statement says "is a member of"; the cabinet's folder
   tab reads "member of political party". Most of the engineering is in this translation step.
3. **A missing file means two different things.** If the cabinet is authoritative for prerequisites
   and a claimed prerequisite isn't there, the claim is *wrong*. If the cabinet was never meant to
   track teaching staff comprehensively, the same absence means *we can't say*. Collapsing those two
   into "false" is how verifiers produce confident wrong answers.

The system runs locally — nothing leaves the machine.

---

## 2. The verdicts

| Verdict | Plain meaning |
| --- | --- |
| **Supported** ✅ | The records back this up. |
| **Contradicted** ❌ | The records say something incompatible. |
| **Not-in-KG** ❔ | The records can't settle it — either genuinely absent, or we couldn't identify what the claim is about. |
| **Out-of-scope** ⬜ | Not a claim these records could ever check — or nothing checkable could be parsed out. |

`Out-of-scope` is a **non-answer**, not a judgement about the world. If the pipeline crashes on a
row, that row is recorded as unscored and left out of the accuracy denominator entirely — see
[§6](#6-the-lesson-that-shaped-the-instrumentation).

---

## 3. The three steps

### Step 1 — Chop the statement into claims

An LLM breaks the statement into `(subject, relation, object)` records. It is given the **menu of
relation types the records can actually answer** and told to mark anything else `unclassified`, which
becomes `Out-of-scope`. This stops the model force-fitting a claim into the wrong category.

To catch small-model mistakes, this runs **twice** at slightly different temperatures and keeps only
claims both runs agree on. The agreement rate is reported.

> **One honest caveat.** The double-run is skipped when the graph being checked against has fewer
> than 50 entities, and the agreement is then recorded as a perfect 1.0. For one benchmark (FactKG),
> where a tiny per-claim graph is built on the fly, this means most rows get a single pass — and
> which rows depends on the claim. So agreement figures are not comparable across datasets.

### Step 2 — Translate claims into filing-cabinet terms

Three separate translations, each of which can **refuse**:

**Who is this about?** Try an exact code, then an exact name match, then fuzzy similarity. Fuzzy
matches are only accepted above a **confidence bar**. Below the bar the system says "I don't know who
this is about" → `Not-in-KG`.

> This bar used to be set very low, which sounds harmless but wasn't: it meant the system *never*
> admitted not recognising a subject. Faced with a person genuinely absent from the records, it
> picked the closest name it had and confidently checked the wrong file. The bar is now tuned on a
> **separate set of data held back for the purpose**, never on the data being scored.

**Which field?** The claim's relation is matched against the fields that actually exist on that
record. This is what handles "is a member of" → "member of political party". Without it the system
returns "can't confirm" for facts sitting right there in the file.

**What value?** This one is subtle and cost a lot of accuracy. Files are *labelled* by id
(`Q295919`) but their *contents* are written as ordinary text (`rhythm and blues`). The system used
to look up the claim's value, get back the id, and then compare an id against text — which never
matches. So *every true claim* came back "contradicted". It now converts back to the text form before
comparing.

### Step 3 — Check the records, and decide what absence means

For a fact that's present, comparison is direct. For a fact that's **absent**, the answer depends on
whether the records are treated as authoritative for that field:

- treated as authoritative → absence means **Contradicted**
- not authoritative → absence means **Not-in-KG**

The system decides this by measuring **how often that field is filled in across the records it has
loaded**, with a cut-off at 85%.

> **Be careful what this measures.** It tells you how *tidily filled-in* the loaded records are. It
> does **not** tell you whether the records cover the real world. On a small or patchy graph a field
> can look "authoritative" simply because the handful of records present happen to have it filled.
> Doing this properly — actually estimating coverage — is designed but not built
> ([`design.md`](design.md)). Everywhere the code and docs say *occupancy*, that is deliberate; it is
> not completeness.

Finally, claim verdicts combine worst-first: any `Contradicted` wins, then `Not-in-KG`, then
`Out-of-scope`, else `Supported`.

---

## 4. What about confidence?

Every verdict carries a confidence number, computed by multiplying together how well the subject
matched, how well the two decomposition passes agreed, and how filled-in the relevant field is.

> [!WARNING]
> **This number has never been checked against how often the system is actually right.** It is a
> plausible-looking composition, not a calibrated probability. Every saved row is stamped
> `confidence_calibrated: false`.
>
> That has a concrete consequence: **the system cannot promise a false-alarm rate.** There is a
> risk-budget controller in the codebase (`abstention_controller.py`) and it behaves correctly — it
> refuses to act on uncalibrated risk, so it always defers to a human. It is never exercised by a
> benchmark run.
>
> Where reports quote "coverage" and "selective accuracy", read those as *descriptions of one
> operating point*, not guarantees.

---

## 5. How we know whether it works

Three habits do most of the work here.

**Recompute everything from individual rows.** Every run saves one record per example, and all
headline numbers are recomputed from those records rather than trusted from the harness. This is not
bureaucracy: a 22.6% crash rate once presented itself as 81.4% accuracy, and a class the system had
essentially stopped predicting sat invisibly inside a plausible-looking overall score. Neither was
detectable without opening the rows.

**Always print the "just guess the commonest answer" score.** An accuracy is meaningless without it.
One benchmark cell in an earlier study turned out to be statistically indistinguishable from always
guessing.

**Destroy the graph and check the answers change.** This is the single most useful test. Shuffle every
value between records — keeping the structure identical, so nothing looks broken — and re-run. If the
verdicts barely move, the system was never really reading the graph. Before the value-namespace fix
described in Step 2, destroying the entire graph changed under 3% of answers. It now changes about
29%. Any change to the translation or checking steps has to keep passing this.

**And know the noise floor.** Running the same evaluation twice changes 0.2–10% of individual answers,
depending on the model, even though the overall accuracy barely moves — offsetting errors cancel out.
So differences smaller than about 2.5 points mean nothing from a single pair of runs. One change was
shipped *disabled* for exactly this reason: it looked like a small improvement, but the improvement
was smaller than the noise.

---

## 6. The lesson that shaped the instrumentation

The most instructive failure in this project wasn't a wrong answer — it was a crash counted as a right
answer.

A bug made the pipeline raise an exception on 22.6% of one benchmark's rows. The evaluation harness
caught each exception and substituted the dataset's default label. That default happened to be the
most common answer in the data, so **113 crashes were scored as 111 correct predictions**. The
benchmark reported 81.4% accuracy when the defensible range was 59.2%–81.4%.

The fix that mattered was not the bug. It was the rule that a crash is **not a prediction**: failed
rows are now recorded as unscored and excluded from the denominator, with the count reported alongside
every accuracy. A tool that converts its own failures into apparent success is worse than a tool that
fails loudly.

---

## 7. Where it stands

**Working:** decomposition, translation, checking, tri-state verdicts, the destruction-based grounding
test, row-level recomputation, held-out threshold tuning.

**Not built:** real completeness estimation, calibrated abstention with a controllable false-alarm
rate, draft generation, a human-review interface, temporal scoping by academic year, provenance links
back to source documents.

**Known-weak evidence:** the institutional benchmark is circular — it checks a sentence that was
generated by filling in the very fields the checker then looks up — so its high accuracy measures
round-tripping through the translation step, not advising quality.

The honest summary: the parts that read a graph and return a three-way verdict work and are
demonstrably reading the graph. The parts that would let anyone *trust a number* — calibration, real
completeness estimation, a non-circular benchmark — are still ahead.
