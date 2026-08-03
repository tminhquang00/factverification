# Comprehensive Incompleteness-Aware Verification Study

**Run date:** 2026-08-03
**Models:** `azure-4.1-mini` and local `google/gemma-4-e4b` through LM Studio
**Status:** automated candidate evidence; no human validation
**Primary artifact directory:** `output/experiments/incompleteness_final_20260803/`

## Executive verdict

The direction has a defensible research contribution, but the current automated evidence is not
journal-ready.

The strongest supported result is a controlled failure characterization: when a verifier collapses
missing graph evidence into contradiction, false-contradiction rate rises sharply as relation facts
are deleted. Explicit relation-completeness declarations prevent that semantic error in the
symbolic verification stage, while a live occupancy heuristic behaves non-monotonically and binary
external checkers cannot express `Not-in-KG`.

The contribution is not atomic decomposition, graph verification, or a new dataset by themselves.
Those already have substantial prior art. The plausible contribution is their junction:

> A controlled methodology and end-to-end error analysis for measuring how post-hoc LLM factuality
> verification changes under knowledge-graph incompleteness, using explicit completeness metadata
> and false-contradiction risk as first-class experimental variables.

The result is strong enough for a master's thesis and potentially a workshop, short paper, or
resource/methodology paper. A competitive full conference paper would need independent validation
and natural-incompleteness evidence. A journal claim is not supported without those additions.

## 1. What the percentages mean

The `100/95/90/80/50/20%` values are **nominal relation-fact retention targets**.

- `100%`: no selected facts are deleted.
- `80%`: approximately 80% remain and 20% are deleted.
- `50%`: approximately half remain.
- `20%`: approximately 20% remain and 80% are deleted.

They are not accuracy, confidence, question coverage, answer sampling, or decomposition agreement.
All 11,647 NUSMods module nodes remain in every graph.

The degraded relations are credit value, faculty/school, prerequisites, preclusions, and offered
semesters. Staffing is not degraded; it is the naturally incomplete open-world anchor.

Random deletion removes individual facts and reaches its target up to integer rounding. Clustered
deletion removes department groups, so realized retention can differ materially by relation. For
example, one nominal clustered 80% graph retained 82.2% of credit facts, 80.3% of school facts,
79.9% of prerequisite facts, 68.5% of preclusion facts, and 79.8% of offered-term facts. Every
manifest records both requested and realized retention.

Each answer is separately decomposed twice. “Two-pass self-consistency” means that only normalized
claims agreeing across the two decomposition calls are kept; it has no connection to the retention
percentage.

## 2. System implemented

The final pipeline performs:

1. long-form answer generation under closed-book, full graph-context, or 50%-degraded graph-context;
2. two-pass schema-guided claim decomposition;
3. entity linking with exact IDs, normalized labels, dense similarity, and NIL rejection;
4. schema-gated relation normalization;
5. deterministic relation-specific graph verification;
6. completeness routing through explicit declarations, occupancy inference, or binary collapse;
7. claim and answer aggregation with row-level provenance.

Important repairs made during the study include deterministic generation and manifests, explicit
empty-set semantics, preclusion and semester verification, numeric normalization, canonical edge
objects without target nodes, relation occupancy caching, claim-local confidence, safe second-pass
failure handling, conservative institutional relation aliases, recovery of values embedded in
Gemma predicate phrases, and independent mechanical rescoring.

The final relation-value repair was discovered empirically: Gemma sometimes emitted
`relation="is offered in Term 2", object=null`. Mapping only the relation name lost the term value.
The final mapper recovers schema-shaped term, credit, prerequisite, or preclusion values from such a
predicate. Python null is no longer interpreted as the literal negation “none.”

## 3. Experimental design

### 3.1 Inputs

- NUSMods: 11,647 entities; 200 questions; 300 distinct expected triples; nine question types.
- RMIT: 50 entities; 50 questions; 66 distinct expected triples; seven question types.
- NUSMods degradation: three seeds, two modes, six retention levels.
- RMIT degradation: three seeds, two modes, three retention levels.
- Public transfer: RMIT, NUSMods, FactKG, and CoDEx.

The 24 NUSMods staffing triples are open-world anchors. Expected-fact extraction metrics exclude
them because the graph does not assert a staff value; open-world verification diagnostics retain
them.

### 3.2 Model matrix

The NUSMods long-form study reuses the same answers across detector arms:

| Answer generator | Claim detector | Purpose |
| --- | --- | --- |
| Azure | Azure | Hosted self-detector |
| Gemma | Gemma | Local self-detector |
| Azure | Gemma | Detector effect on identical Azure answers |
| Gemma | Azure | Detector effect on identical Gemma answers |

Answer temperature is `0.2`; decomposition uses `0.1` and `0.2`. Cross-model rows therefore hold
answer text fixed, but decomposition remains stochastic. Differences are highly informative but are
not deterministic paired causal estimates.

### 3.3 Systems and baselines

- `declared`: absence follows an explicit relation completeness declaration.
- `binary`: `Not-in-KG` is collapsed into `Contradicted`.
- `occupancy`: complete/incomplete is inferred from current graph field density at thresholds
  `0.50/0.70/0.85/0.95`.
- flat-context LLM: the model receives the relation-specific graph snippet and emits a tri-state
  verdict. This is oracle-selected context, not a deployed retriever.
- MiniCheck: binary Supported/Unsupported fact checking. Unsupported is naively mapped to
  Contradicted only to expose the open-world mismatch.

### 3.4 Statistics

Incompleteness intervals use 1,000 bootstrap samples clustered by `(deletion seed, question_id)`.
Rates with zero predicted decisions are undefined (`null`), not reported as zero. Paired system
differences are computed on identical atoms. Calibration uses a question-grouped 50/50
calibration/test split and binomial upper bounds; it is a diagnostic, not conformal risk control.

## 4. Results

### 4.1 Deterministic ceilings and controls

| Control | Result |
| --- | ---: |
| Gold expected triples -> verifier | 100.0% |
| Gold expected triples -> linker -> verifier | 100.0% |
| Stage 4 on Azure-extracted atoms | 100.0% |
| Stage 4 on final Gemma-extracted atoms | 100.0% |
| NUSMods shuffled-graph prediction change | 34.76% (PASS) |
| CoDEx shuffled-graph prediction change | 29.53% (PASS) |
| RMIT set control: shuffle accuracy drop | 42.4 points |
| RMIT set control: empty-graph drop | 51.5 points |

Both destruction controls exceed the required 20% prediction-change gate. The perfect oracle
ceiling shows that the graph schema and symbolic verifier can represent the expected triples; it
does not imply perfect end-to-end extraction.

### 4.2 Stage-wise end-to-end attribution

Expected-triple F1 on full-context answers:

| Generator -> detector | Extraction coverage | Expected-triple F1 | Exact expected set |
| --- | ---: | ---: | ---: |
| Azure -> Azure | 87.5% | 98.6% | 96.6% |
| Azure -> Gemma | 80.0% | 91.1% | 79.0% |
| Gemma -> Azure | 76.5% | 87.4% | 77.8% |
| Gemma -> Gemma | 70.0% | 79.7% | 65.3% |

Azure self-detection changes strongly with evidence: expected-triple F1 is 23.2% closed-book,
63.0% with degraded context, and 98.6% with full context. Its Stage 4 accuracy on whatever was
successfully extracted is 100%; most end-to-end loss is missing or altered claims before Stage 4.

The cross-detector arms separate model roles. On identical Gemma answers, changing the detector from
Gemma to Azure raises full-context expected-triple F1 by 7.7 points. On identical
Azure answers, changing Azure to Gemma lowers it by 7.5 points. Holding the detector fixed, Azure
answers outperform Gemma answers by about 11.2-11.4 points. Both stages matter: answer content is
the larger model-dependent gap, and Gemma decomposition/typing adds a second measurable loss.

### 4.3 Headline false-contradiction curve

Final pooled random-deletion results, across three seeds and all generation conditions:

| Generator -> detector | System | 100% FCR | 80% FCR | 50% FCR | 20% FCR |
| --- | --- | ---: | ---: | ---: | ---: |
| Azure -> Azure | Binary | 5.1% | 63.6% | 88.8% | 96.3% |
| Azure -> Azure | Declared | 0.0% | 0.0% | 0.0% | 0.0% |
| Azure -> Gemma | Binary | 17.5% | 71.8% | 92.6% | 97.7% |
| Azure -> Gemma | Declared | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemma -> Azure | Binary | 40.9% | 86.9% | 95.8% | 98.6% |
| Gemma -> Azure | Declared | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemma -> Gemma | Binary | 62.5% | 90.1% | 96.4% | 99.1% |
| Gemma -> Gemma | Declared | 0.0% | 0.0% | 0.0% | 0.0% |

Question/seed-clustered 95% intervals confirm that the endpoint change is far beyond sampling
uncertainty. Azure self-detection moves from 5.1% `[2.3, 7.8]` to 96.3% `[94.9, 97.6]`; Gemma
self-detection moves from 62.5% `[52.4, 72.3]` to 99.1% `[98.4, 99.7]`. The non-zero 100% values
come from naturally missing staffing facts and unresolved/extraneous generated claims, which binary
collapse is forced to call contradictions even when the graph itself is intact.

At random 20%, the paired declared-minus-binary accuracy difference is +68.3 points
`[64.9, 72.1]` for Azure self-detection and +78.2 `[75.1, 81.4]` for Gemma self-detection. These are
differences under the mechanically defined semantics, not independent effect estimates on human
truth labels.

The same qualitative curve appears under clustered deletion. For Azure self-detection, binary FCR
rises from 5.1% at full retention to 97.2% at nominal clustered 20%. The declared route remains at
zero false contradictions under mechanical labels while decision coverage falls from 99.3% to
roughly 29%: safe abstention replaces false certainty.

The occupancy baseline is not stable. At threshold 0.50 in the Azure self arm, random-deletion FCR
is 20.2% at 95%, 44.5% at 80%, and 80.1% at 50%, then falls to zero at 20% because the relation
density finally crosses the threshold and the route becomes open. This non-monotonicity is exactly
why current occupancy cannot stand in for declared completeness.

The proposed route's perfect mechanical score must be interpreted narrowly. Gold and routing do not
call the same Stage 4 implementation, but they share the same researcher-authored declarations and
graph semantics. This demonstrates semantic consistency, not independent real-world correctness.

### 4.4 External verifier baselines

#### Azure flat-context, oracle-selected evidence

| Mode | Retention | Tri-state accuracy | Binary-collapse accuracy | False-support rate |
| --- | ---: | ---: | ---: | ---: |
| Random | 100% | 92.0% | 92.0% | 8.0% |
| Random | 80% | 83.3% | 77.7% | 10.7% |
| Random | 50% | 72.7% | 51.3% | 16.3% |
| Random | 20% | 64.3% | 24.7% | 33.3% |
| Clustered | 20% | 80.7% | 23.0% | 31.0% |

There were zero call failures in 2,700 unique Azure classifications. The tri-state prompt is much
safer than binary collapse, but still degrades and sometimes labels missing-evidence cases
Supported or Contradicted. Every predicted contradiction in incomplete conditions was false in this
expected-true-triple design, although counts range from 2 to 70 per condition and must be read beside
the rate.

Gemma is weaker under the same oracle-context protocol:

| Mode | Retention | Tri-state accuracy | Binary-collapse accuracy | False-support rate |
| --- | ---: | ---: | ---: | ---: |
| Random | 100% | 87.3% | 79.3% | 0.0% |
| Random | 80% | 74.0% | 65.0% | 2.0% |
| Random | 50% | 55.0% | 43.0% | 3.0% |
| Random | 20% | 36.7% | 21.7% | 3.0% |
| Clustered | 20% | 46.0% | 21.3% | 0.0% |

All 2,700 Gemma classifications have a final prediction and none has a terminal call error. As in
the Azure arm, every predicted contradiction is false in this expected-true-triple design. The
checkpointed run resumed after 200 tasks; its saved token-usage snapshot therefore covers only the
final process segment, while the row-level prediction artifact covers all 2,700 tasks.

#### MiniCheck

MiniCheck completed 2,700 unique inferences on CPU. Native binary accuracy rises from 71.3% at full
retention to 83.3% at random 20%, largely because missing-evidence documents become easier to call
Unsupported. But a binary checker cannot distinguish `Not-in-KG` from contradiction: naively mapping
Unsupported to Contradicted yields 100% FCR in every condition and tri-state accuracy falls from
71.3% to 17.0% at random 20% (13.7% clustered).

This is not evidence that MiniCheck is poor at its intended binary task. It is evidence that its
label space is insufficient for the open-world decision required here.

### 4.5 NIL entity linking

The 1,000-example title-only held-out stress test contains 500 active and 500 held-out entities. At
the deployed 0.95 threshold:

- total exact/NIL link accuracy: 57.2%;
- In-KB precision/recall/F1: 68.5% / 37.4% / 48.4%;
- NIL precision/recall/F1: 62.9% / 77.0% / 69.2%;
- accepted-link coverage: 38.8%.

At 0.99, total accuracy is only 58.2%. Ambiguous title-only mentions impose a hard limit: duplicate
or generic course titles cannot prove that a mention belongs to an active rather than held-out
entity. Course-code linking is perfect in the oracle attribution arm, so realistic deployment should
preserve identifiers or add a stronger context-aware linker.

### 4.6 RMIT and public transfer

Hosted final public results (random sampling where applicable):

| Dataset | Azure accuracy | Macro-F1 | Notes |
| --- | ---: | ---: | --- |
| RMIT, 300 rows | 97.0% | 98.2% | Institutional synthetic claim transfer |
| NUSMods, 500 rows | 99.8% | 99.8% | Tri-state catalog benchmark |
| CoDEx, 500 rows | 84.8% | 84.5% | Open-domain tri-state |
| FactKG, 500 rows | 60.4% | 50.2% | Binary labels; random sample |

Local final results (random sampling where applicable):

| Dataset | Gemma accuracy | Macro-F1 | Notes |
| --- | ---: | ---: | --- |
| RMIT, 300 rows | 75.0% | 80.3% | 88.0% decision coverage; 85.2% selective accuracy |
| NUSMods, 500 rows | 99.4% | 99.4% | Same result under prefix and random sampling |
| CoDEx, 500 rows | 79.8% | 79.7% | Prefix accuracy is 77.0% |
| FactKG, 500 rows | 59.0% | 47.4% | Prefix accuracy is 82.4%; random is the headline |

All seven local cells exit successfully with zero harness failures and start-time code hashes in the
process manifest. Relative to Azure, Gemma is 22.0 points lower on RMIT, 0.4 lower on NUSMods, 5.0
lower on random CoDEx, and 1.4 lower on random FactKG. The local FactKG prefix/random difference is
23.4 points, independently reproducing the sampling-composition warning.

FactKG exposes a major evaluation pitfall. Prefix sampling gives Azure 82.0% but covers only two
ordered reasoning blocks and has a 64.6% majority floor; random sampling gives 60.4%. The 21.6-point
difference is sampling composition, not a model improvement. Prefix results are retained only as a
bias diagnostic.

RMIT repeats the main pattern on a smaller graph. Full-context expected-triple F1 is 78.8% for
Azure (100% extraction coverage; 72% exact expected sets) and 67.8% for Gemma (80% coverage; 52%
exact sets); Stage 4 on extracted atoms and both oracle stages remain 100%. Under random deletion,
binary FCR rises from 4.8% to 95.3% for Azure and from 64.7% to 98.7% for Gemma between 100% and
20% retention. Declared FCR is zero under mechanical labels in every RMIT condition.

### 4.7 Confidence and selective risk

On the held-out test split for Azure self-detection, the binary system can meet the 5% diagnostic
false-contradiction target only at confidence `1.0`, accepting 138 of 3,419 contradiction decisions
(4.0% decision coverage). The declared route accepts all 858 test contradiction decisions with zero
mechanical-label errors; its one-sided binomial upper bound is 0.35%. This is evidence of the
coverage cost of trying to rescue binary routing with the current score, not a safety guarantee.

The all-row expected calibration error is 0.062 for binary and 0.119 for declared in this arm. A
perfect mechanical classification can therefore have worse ECE because the confidence formula is
not fitted to correctness. Confidence should not be used as a probability.

The calibration artifact explicitly disclaims a conformal guarantee. Correlated repeated atoms,
mechanical labels, and the heuristic confidence score prevent a deployment-safety claim.

## 5. Interpretation

### Finding 1: missing evidence and contradiction are empirically different

Binary collapse converts almost every increasingly common missing-fact case into a false
contradiction. The curve is steep, reproducible across random and clustered deletion, and present
across generator/detector pairings.

### Finding 2: explicit declarations solve the symbolic routing problem

When relation metadata says that a degraded relation is incomplete, Stage 4 returns `Not-in-KG`
for absence while retaining contradiction for incompatible values. This behaves consistently under
controlled deletion. Occupancy does not: it depends on the current damaged graph and can reverse
its behavior as density crosses a threshold.

### Finding 3: decomposition dominates the end-to-end error budget

Oracle linking and verification reach 100%, and Stage 4 on canonical extracted atoms reaches the
same ceiling. Expected-triple F1 changes much more with detector model and retrieval condition than
with symbolic verification. The research paper should therefore present the system as an
incompleteness-aware verification framework with explicit stage attribution, not as a universally
accurate end-to-end detector.

### Finding 4: a tri-state prompt helps but is not equivalent to declared semantics

Even with oracle-selected relation context, the hosted LLM's tri-state accuracy falls as facts are
removed and its false-support rate rises. A natural-language instruction to say “unknown” is useful,
but does not provide the deterministic semantic control of explicit relation metadata.

### Finding 5: model scale matters most before the symbolic core

The hosted detector extracts substantially more complete, schema-valid claim sets. Once a correct
triple reaches Stage 4, both model paths share the same deterministic verifier. This suggests a
practical hybrid: local generation, stronger decomposition/typing, then local symbolic verification.

## 6. Relation to prior work and novelty boundary

Atomic claim decomposition and retrieval-grounded factuality are established by systems such as
[FActScore](https://aclanthology.org/2023.emnlp-main.741/),
[SAFE](https://arxiv.org/abs/2403.18802),
[RefChecker](https://aclanthology.org/2024.emnlp-main.395/), and
[VeriScore](https://aclanthology.org/2024.findings-emnlp.552/). Efficient binary evidence checking is
the goal of [MiniCheck](https://aclanthology.org/2024.emnlp-main.499/). FactKG already studies
fact verification over knowledge graphs ([ACL 2023](https://aclanthology.org/2023.acl-long.895/)).

Knowledge-base completeness statements and partial closed-world reasoning also predate this work
([Darari et al. 2014](https://arxiv.org/abs/1408.6395),
[fine-grained completeness statements](https://arxiv.org/abs/1604.08377)). A modern survey covers
KG completeness and recall more broadly ([survey](https://arxiv.org/abs/2305.05403)). Recent work on
KG-RAG incompleteness and incomplete-KG completion means that “KGs are incomplete” cannot itself be
claimed as novel ([KG-RAG study](https://arxiv.org/abs/2504.05163),
[MusKGC](https://aclanthology.org/2025.emnlp-main.508/)).

The narrower gap is that long-form post-hoc factuality work rarely treats source completeness as
explicit metadata whose controlled degradation is evaluated through asymmetric false-contradiction
risk. That is the defensible novelty claim. A literature review must phrase it as a gap supported by
the reviewed sources, not as proof that no prior paper exists.

## 7. Publication assessment

### What can be claimed now

- Controlled relation-fact deletion makes completeness dependence measurable.
- Binary absence handling causes a steep false-contradiction curve.
- Explicit completeness declarations implement the intended tri-state semantics.
- Occupancy is an unreliable substitute for declared completeness.
- Binary external fact checkers cannot represent `Not-in-KG` without a semantic error.
- Stage attribution identifies decomposition, not symbolic lookup, as the main end-to-end bottleneck.

### What cannot be claimed now

- independently validated real-world factuality accuracy;
- journal-level superiority over established factuality systems;
- realistic retrieval performance—the context arms use oracle subject/relation selection;
- institution-authorized correctness of completeness declarations;
- conformal or calibrated deployment safety;
- broad generalization beyond catalog schemas and the two public benchmarks.

### Venue judgment

| Target | Current readiness | Reason |
| --- | --- | --- |
| Master's thesis | Yes | The methodology, implementation, controls, and negative/positive findings form a coherent thesis. |
| Workshop/short paper | Plausible now | The controlled FCR curve and semantic ablations are a focused contribution if limitations are explicit. |
| Full conference paper | Borderline | Needs independent labels or a naturally incomplete external graph, realistic retrieval, and repeated stochastic runs. |
| Journal | No | Current gold/declarations share researcher semantics and the study intentionally skipped human validation. |

Skipping human review was respected. The consequence is not that the experiment is useless; it is
that the strongest valid paper is a controlled methodology/failure-analysis paper rather than an
independent efficacy paper.

## 8. Threats to validity

- Mechanical gold and declared routing share graph/declaration semantics.
- Deletion is simulated. Clustered deletion is more realistic than uniform deletion but is still a
  proxy for institutional data loss.
- Questions and expected triples are graph-derived.
- One answer-generation run per generator/condition does not estimate LLM variance.
- Cross-detector decompositions are stochastic even with identical answer text.
- The local Gemma model often omits or mis-types atoms; two-pass agreement can trade recall for
  precision.
- The flat-context baseline receives oracle-selected context.
- The NIL test uses deliberately difficult title-only mentions and does not represent code-rich
  administrative queries.
- RMIT has only 50 graph entities and 50 long-form questions.
- FactKG is binary and ordered by reasoning type; sampling method changes the apparent result.
- The confidence score is heuristic and the calibration diagnostic is not a guarantee.
- Data redistribution rights for source catalog records require a separate release review.

## 9. Reproducibility and authoritative artifacts

| Evidence | Authoritative artifact |
| --- | --- |
| NUSMods questions/provenance | `data/nusmods_questions_200.jsonl`, `data/nusmods_questions_200.manifest.json` |
| RMIT questions/provenance | `data/rmit_questions_50.jsonl`, `data/rmit_questions_50.manifest.json` |
| NUSMods multi-model deletion rescore | `nusmods_rescore_authoritative.json` and `_analysis.json` |
| NUSMods stage attribution | `nusmods_stage_attribution_authoritative.json` |
| NUSMods calibration diagnostic | `nusmods_rescore_authoritative_calibration.json` |
| Model-free ceilings | `nusmods_oracle_sweep_final.json`, `rmit_oracle_sweep_final.json` and analyses |
| Azure/Gemma oracle-context baselines | `nusmods_flat_azure.json`, `nusmods_flat_gemma.json` and analyses |
| MiniCheck baseline | `nusmods_minicheck.json` and `nusmods_minicheck_analysis.json` |
| NIL linker sweep | `linker_nil.json` |
| Destruction controls | `nusmods_destruction_control.json`, `codex_destruction_control.json`, `rmit_set_destruction.summary.json` |
| RMIT long-form transfer | `rmit_rescore_authoritative.json`, `rmit_stage_attribution_authoritative.json` |
| Hosted public transfer | `final_public_20260803_azure/aggregate_summary.json` and `process_manifest.json` |
| Local public transfer | `final_public_20260803_local/aggregate_summary.json` and `process_manifest.json` |
| Regression evidence | `full_test_suite_authoritative.log` |

Unless a path begins with `data/` or a public run directory, table entries are under
`output/experiments/incompleteness_final_20260803/`.

All reported aggregates are derived from saved row-level JSON. Long-running pilots record model and
provider identity, answer reuse, calls, failures, tokens where exposed, elapsed time, input hashes,
and script/pipeline hashes captured before model calls. Public sweep manifests record exact command
lines, timestamps, exit codes, and code identity for the final affected cells.

The final regression suite result is **101 tests passing**. Historical output directories are retained
for forensic comparison but are not current evidence.

## 10. Recommended next research step

If publication beyond a workshop is desired, the minimum high-value extension is not another large
model sweep. It is:

1. obtain independent labels for a stratified sample of full, deleted, conflicting, and naturally
   absent claims;
2. obtain or emulate declarations from a source owner rather than the benchmark author;
3. replace oracle context selection with a real retriever and report retrieval recall separately;
4. repeat answer generation at least three times per model/condition;
5. add a naturally incomplete graph or time-sliced snapshot pair;
6. fit and evaluate a genuinely independent risk-control layer.

Those steps would convert the current semantic demonstration into a stronger empirical systems
paper. Without them, adding more automated rows mainly narrows uncertainty around the same
mechanically defined estimand.
