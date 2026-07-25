# Research Improvement Plan: Completeness-Aware KG Verification

**Working title:** Completeness-Aware Verification of LLM Responses over Institutional Knowledge Graphs: A Tunable Abstention Architecture for University Course Advising  
**Evidence review date:** 2026-07-24

## 1. Executive Decision

The research direction is worthwhile, but the current repository does not yet implement or validate the central construct in the title: completeness of an LLM answer relative to the complete, query-scoped answer set.

The current system is primarily a claim-level correctness verifier. It decomposes text into triples, links entities, checks individual triples, and can downgrade a low-confidence `Contradicted` verdict to `Not-in-KG`. This is useful infrastructure, but it does not detect that a response omitted one of several prerequisites, electives, coordinators, or degree requirements.

The paper should therefore be rebuilt around one precise primary contribution:

> Given a versioned institutional KG and a scope-bounded set-valued advising query, compute the KG-derived expected answer set, measure which required answers the LLM included or omitted, and defer the response when calibrated omission or false-contradiction risk exceeds institution-selected budgets.

The shuffled-KG control and per-relation completeness metadata can remain important secondary contributions. Current benchmark numbers and reports should be treated as provisional until the validity issues below are fixed and every table is regenerated from recorded predictions.

## 2. What the Repository Currently Implements

### Implemented

- LLM claim decomposition into schema-guided triples in [`verification_pipeline.py`](../verification_pipeline.py).
- Course-code, exact, embedding, and token-overlap entity linking.
- Deterministic checks for credits, school, coordinator, and prerequisite relations.
- Tri-state claim verdicts: `Supported`, `Contradicted`, and `Not-in-KG`.
- Claim-level evidence strings and reasons.
- A contradiction-only abstention rule using a configurable instance field.
- Synthetic institutional claim datasets and adapters for public fact-verification datasets.
- Initial shuffled-object controls and completeness-profile generation scripts.

### Partially implemented

- Per-relation world-assumption routing exists as a binary density threshold, but the main verifier does not consume the offline adapter profiles and the experiment's `cwa_threshold` setting is not read by the verifier.
- Provenance contains evidence text, but not graph version, source record, extraction path, linking method, prompt/model version, or stage-level scores.
- Selective prediction exists for low-confidence contradictions, but the score is not empirically calibrated and is not an answer-completeness score.
- Linking conditions exist as scattered flags/fallbacks, but L0/L1/L2 are not clean, mutually exclusive experimental treatments across all datasets.

### Not implemented

- Query intent and scope parsing for set-valued advising questions.
- Computation of an expected answer set or certain answers from the KG.
- Answer-set extraction and matching.
- Omission detection, answer recall, exact-set match, or completeness verdicts.
- A separate risk estimate for accepting an incomplete answer.
- Conformal or other statistically calibrated risk control.
- An administrative cost model evaluated over real predictions.
- A real advisor-authored or advisor-audited course-advising answer benchmark.

## 3. Findings That Block Interpretation of Current Results

### P0.1 Dataset stores are not isolated

`get_kg_store()` returns one process-global singleton regardless of `graph_json_path`. A runtime probe created RMIT, Catalog2, and CoDEx pipelines in one process and observed the same store object, the same RMIT path, and the same 50 courses in all three pipelines. Any script that constructs multiple dataset pipelines in one process can evaluate later datasets against the first graph loaded.

Required action: remove the path-insensitive singleton. Cache immutable stores by canonical graph path only if caching is needed.

### P0.2 Concurrent evaluation mutates shared state

The evaluation harness shares a pipeline across worker threads. Public-dataset evaluation clears and repopulates `pipeline.store.courses`, rebuilds the shared entity index, and updates `last_entity_score` and `last_decomp_agreement`. These operations can interleave across examples and corrupt triples, links, confidence scores, and abstention decisions.

Required action: make stores immutable during evaluation and use a per-example verification context. Do not store claim-local scores on the pipeline instance.

### P0.3 The reported routing ablation does not change routing

`run_e2_routing_ablation()` assigns `pipeline.cwa_threshold`, but no verifier code reads that attribute. `dynamic`, `fixed_cwa`, and `fixed_owa` are therefore not valid treatments. Small differences can arise from nondeterministic LLM calls and shared-state races, not world-assumption policy.

Required action: define one explicit routing policy interface and inject it into the verifier. Unit-test each policy on the same pre-linked triples before running an end-to-end ablation.

### P0.4 Several reported experiments are generated rather than measured

- The E3 denominator ablation returns constants.
- The E4 threshold sweep generates coverage and accuracy from formulas rather than pipeline predictions.
- The E5 path can fall back to a synthetically separable balanced dataset.
- Existing meta-confidence feature construction includes label-dependent synthetic confidence values.

Required action: prohibit hard-coded metrics in experiment code. Every aggregate must be reproducible from a saved row-level prediction artifact.

### P0.5 The shuffled-KG artifact lacks its paired baseline

The Phase 0 script saves shuffled accuracies but not baseline predictions from the same items, decomposition outputs, and linking condition. The report also includes an RMIT shuffled result that is not produced by that script.

Required action: save paired baseline and shuffled predictions for every sample and permutation seed. Cache decomposition/linking before corruption so the control changes only graph evidence.

### P0.6 Reported statistical procedures are not implemented

The harness uses item-level bootstrap resampling, while the report says intervals are clustered by subject. The report states Holm-Bonferroni correction, but no corresponding p-values or correction code are recorded in the result artifact.

Required action: use paired, cluster-aware inference and write raw and adjusted statistics to machine-readable outputs.

### P0.7 Relation density is being called completeness

The offline profile is the fraction of entity records containing a field. This is relation prevalence or field occupancy, not evidence that all true values are recorded. It also ignores relation applicability. A course with no prerequisites can make an empty prerequisite field correct and complete, while a sparse coordinator relation may be fully complete for the subset of courses where a coordinator applies.

Current RMIT and Catalog2 profiles contain only `1.0` values. The runtime RMIT graph also gives `taughtBy = 1.0`, so the motivating high-completeness credits versus low-completeness coordinators contrast is not present in the current data.

Required action: rename occupancy metrics and estimate completeness against an applicable population using audits, source snapshots, or explicit completeness declarations.

### P0.8 The institutional benchmark is not an advising-answer benchmark

`generate_dataset.py` produces individual true, perturbed, fake, and multi-hop claims from the same KG used for verification. It does not contain user context, degree rules, query scope, expected answer sets, or intentionally partial LLM answers.

Required action: create a new benchmark whose unit is `(query, student/context, KG version, expected answer set, candidate response)`.

### P0.9 Public tri-state held-out edges are not actually held out

The CoDEx and MetaQA tri-state builders mark records as `is_held_out_edge`, but the true edge remains in the background graph. The record-level triples also include that edge. This does not create a valid `Not-in-KG` condition.

Required action: materialize train/calibration/test graph views or deletion masks and assert that held-out triples are absent from the graph used by the verifier.

## 4. Revised Research Questions

Use a smaller, sharper question set.

### RQ1: Output completeness

Can a versioned institutional KG detect when an LLM response omits required members of a scope-bounded answer set more reliably than claim-only verification and an LLM-as-judge?

### RQ2: Negative evidence under heterogeneous KG completeness

When a candidate fact is absent, do relation- and scope-specific completeness certificates reduce false contradictions compared with fixed closed-world and fixed open-world policies?

### RQ3: Tunable deferral

Can a calibrated two-risk controller meet institution-selected bounds on accepted-answer omission risk and false-contradiction risk while retaining useful automation coverage?

### RQ4: Graph-groundedness

Do performance and decision traces change under controlled graph destruction when language, decomposition, linking, density, and type distributions are held fixed?

## 5. Formalize the Construct Before More Experiments

For query $q$, context $x$, KG version $G_t$, and declared scope $s$, define the expected answer set:

$$
E(q, x, G_t, s) = \operatorname{CertainAnswers}(Q_{q,x,s}, G_t)
$$

Extract and link the answer mentions in candidate response $a$:

$$
M(a, q) = \{\text{linked answer entities or values expressed in } a\}
$$

Define set precision and recall:

$$
P_{set} = \frac{|M \cap E|}{|M|}, \qquad
R_{set} = \frac{|M \cap E|}{|E|}
$$

Use explicit conventions for empty sets. Report exact-set match separately:

$$
\operatorname{ExactSetMatch} = \mathbb{1}[M = E]
$$

The operational completeness label is relative to a source, version, and scope. Avoid claiming real-world completeness when only KG-relative completeness is known.

### Separate three forms of incompleteness

1. **Query incompleteness:** the user omitted variables needed to determine an answer, such as program, career level, campus, or transcript.
2. **KG incompleteness:** the institutional source does not contain all true facts for the requested scope.
3. **Response incompleteness:** the answer omits members of a computable expected set.

This paper should primarily target response incompleteness. PassiveQA targets the first category and some evidence insufficiency; that is a close comparator, not the same task.

### Define relation completeness correctly

For relation $r$ and applicability predicate $A_r(e)$, distinguish:

$$
\operatorname{Occupancy}(r) =
\frac{|\{e : A_r(e) \land \exists o\; r(e,o) \in G\}|}
{|\{e : A_r(e)\}|}
$$

from an audited completeness estimate:

$$
C(r,s,t) =
\Pr(\text{all true } r\text{-values are recorded} \mid r,s,G_t)
$$

Estimate $C(r,s,t)$ from source-specific evidence, not edge density alone. Candidate methods are:

- Explicit source/schema guarantees for mandatory functional fields.
- Stratified manual audits against handbook pages.
- Agreement between independent source snapshots or extraction methods.
- Capture-recapture or positive-unlabeled estimates where appropriate.
- Hand-authored completeness statements for high-stakes relations.

Store a confidence interval and evidence type with each estimate. Do not collapse $C$ to `closed/open` until a deployment policy applies its selected threshold.

## 6. Target Architecture

### Stage A: Query and scope specification

Produce a typed `QuerySpec` containing:

- intent, such as `all_prerequisites`, `remaining_requirements`, or `eligible_electives`;
- subject entity and gold/retrieved/heuristic link provenance;
- student and program constraints;
- temporal KG version;
- answer type and set semantics;
- relation completeness certificate required to interpret absence.

### Stage B: Expected answer-set computation

Use deterministic, tested KG queries to compute $E(q,x,G_t,s)$. Return proof objects containing the query plan, source records, path(s), and scope constraints.

### Stage C: Response decomposition and answer-set extraction

Extract both ordinary atomic claims and answer members. Keep extraction confidence and linking provenance local to each claim/member. Do not let concurrent examples share mutable scores.

### Stage D: Correctness and completeness verification

Produce two independent outputs:

- claim correctness: supported, contradicted, or unknown;
- answer coverage: complete, incomplete, indeterminate, or not set-valued.

An answer may be factually precise but incomplete. Preserve this state rather than collapsing it into one tri-state label.

### Stage E: Dual-risk action controller

Use separate calibrated scores for:

- $p_{wrong}$: risk that a committed factual verdict is wrong;
- $p_{omit}$: risk that an accepted answer omits required information.

The action policy should be explicit:

$$
\pi(a) =
\begin{cases}
\text{accept} & p_{wrong} \le \alpha_w \land p_{omit} \le \alpha_o \\
\text{correct/revise} & \text{missing or contradicted items are recoverable automatically} \\
\text{defer} & \text{risk exceeds budget or the KG certificate is insufficient}
\end{cases}
$$

This two-axis design is preferable to multiplying heterogeneous features into one unvalidated confidence score.

### Stage F: Audit record

Persist:

- raw query and candidate answer;
- query scope and KG snapshot hash;
- prompt, model, and parser versions;
- decomposed claims and answer members;
- linking candidates, selected IDs, scores, and L0/L1/L2 condition;
- expected answer set and proof paths;
- relation completeness certificate and provenance;
- calibrated risks, selected thresholds, action, and human override.

## 7. Benchmark Redesign

### Institutional datasets

Build two genuinely independent catalogs:

1. RMIT, expanded beyond the current 50-course sample and versioned by handbook date.
2. Catalog2, with independent extraction rules and no shared singleton/cache state.

Use at least three set-valued advising intents:

- all direct prerequisites, preserving AND/OR structure;
- all courses eligible under a supplied transcript and term;
- all remaining program requirements under a supplied program plan.

Credits and coordinator values remain useful claim-correctness tasks, but they are not sufficient to demonstrate answer completeness.

### Candidate responses

For each query, create controlled response conditions:

- complete and correct;
- one required item omitted;
- multiple items omitted;
- correct set plus one distractor;
- complete set with one corrupted value;
- fluent paraphrase with implicit answer members;
- scope mismatch;
- answer indeterminate because KG completeness is uncertified.

Generate candidates with multiple LLMs, but also include deterministic perturbations so omission depth and error type are known exactly.

### Gold construction

- Compute initial expected sets with deterministic queries.
- Have two trained annotators or advisors audit query scope, answer set, and source provenance.
- Resolve disagreements and report inter-annotator agreement.
- Split by course/program entity and template family, not by random row, to prevent paraphrase and subject leakage.
- Freeze development, calibration, and final test splits before threshold selection.

### Public benchmarks

Keep FactKG and CoDEx only for claim-verification component tests and graph-destruction controls. They should not support the headline completeness claim.

For external answer-completeness validation, use set-valued KGQA data with gold answer sets, such as MetaQA's native answer lists or a suitable compositional KGQA benchmark. Construct partial candidate responses from the native gold sets, and use a graph snapshot that actually excludes any designated unknown edges.

## 8. Experiment Matrix

### E0: Deterministic component validation

- Store isolation by graph path.
- No mutation under parallel evaluation.
- Exact expected-set query tests.
- Held-out-edge absence assertions.
- Reproducible metrics from row-level artifacts.

Exit criterion: repeated runs on cached decompositions produce byte-identical decisions and metrics.

### E1: Decomposition and linking axis

Run the same examples under mutually exclusive conditions:

- L0: gold entities and relations;
- L1: retrieval/bi-encoder with a frozen index;
- L2: deterministic heuristic linking only.

Report entity accuracy, relation accuracy, answer-member extraction F1, and downstream completeness detection. This separates verifier logic from language/linking errors.

### E2: Claim-level verification

Compare:

- no verifier;
- closed-book LLM;
- context LLM;
- deterministic KG verifier;
- KG verifier plus relation completeness routing.

Report tri-state macro-F1, contradiction precision/recall, false-contradiction rate, and per-relation results.

### E3: Answer-completeness detection

Compare:

- claim-only verifier;
- LLM-as-judge completeness rubric;
- generic factual-recall method;
- exact KG set comparison with L0 links;
- full pipeline with L1 and L2 links.

Report omission detection AUROC/AUPRC, completeness macro-F1, set precision/recall/F1, exact-set match, and performance by expected-set size and omission depth.

### E4: Relation-completeness routing

Compare fixed CWA, fixed OWA, occupancy-threshold routing, audited $C(r,s,t)$ routing, and oracle completeness declarations. Use pre-linked triples so this experiment isolates negative-evidence semantics.

Report false contradictions and missed contradictions per relation. Do not claim dynamic routing dominates unless the paired confidence interval excludes zero and the effect is operationally meaningful.

### E5: Measured abstention operating curves

For every candidate threshold, recompute decisions from saved scores and labels. Report:

- automation coverage;
- accepted-answer incompleteness risk;
- false-contradiction risk;
- omission recall among deferred answers;
- selective accuracy;
- area under the risk-coverage curve;
- institution-specific expected cost.

Use separate curves for query intent, relation class, and catalog.

### E6: Calibration and risk control

Fit thresholds only on the calibration split. Start with transparent isotonic or logistic calibration. Add conformal risk control only after the loss and exchangeability assumptions are explicit.

For each target risk budget, report the empirical test risk and a one-sided confidence bound. A deployment setting is admissible only when the upper bound is below the institution's selected budget.

### E7: Graph-groundedness controls

Use paired controls with cached decomposition and links:

- original graph;
- empty graph;
- within-relation, type-preserving object derangements;
- relation-label permutation;
- text-only/no-graph verifier.

Run multiple permutation seeds. Save per-example paired predictions and ensure derangements do not accidentally retain the original object. Report paired effect sizes and confidence intervals, not only two accuracies.

### E8: Cross-catalog generalization

Develop and calibrate on one institution, then evaluate unchanged on the second. Also report institution-specific recalibration. This tests whether signals generalize or merely encode one catalog's field conventions.

### E9: Advisor-in-the-loop utility

Have advisors review a randomized sample under no verifier, verifier without deferral, and risk-controlled deferral. Measure:

- harmful omissions reaching students;
- false alerts per reviewed answer;
- advisor review time;
- proportion automated;
- agreement with the system's cited missing items;
- expected administrative cost under preregistered cost ratios.

## 9. Administrative Cost Model

Define costs before examining final test results:

$$
L = c_{FC}\mathbb{1}[\text{false contradiction}]
  + c_{MC}\mathbb{1}[\text{missed contradiction}]
  + c_{OI}\mathbb{1}[\text{accepted incomplete answer}]
  + c_D\mathbb{1}[\text{human deferral}]
$$

Report a sensitivity analysis over plausible cost ratios instead of presenting one arbitrary setting. The main deployment result should be a Pareto frontier or policy table showing which thresholds are optimal under different institutional preferences.

## 10. Statistical and Reproducibility Protocol

- Save one row per example, condition, seed, and threshold source score.
- Record data hash, KG snapshot hash, code commit, model/deployment ID, prompt hash, decoding parameters, and timestamp.
- Cache decomposition and linking outputs for graph and threshold ablations.
- Use paired bootstrap or permutation tests for paired system comparisons.
- Cluster intervals by the highest dependency unit, normally course, program, or student scenario.
- Use repeated permutation seeds for shuffled-KG controls.
- Correct multiple comparisons only for a preregistered family of hypotheses and store raw plus adjusted p-values.
- Report effect sizes and confidence intervals even when a significance test is used.
- Never write aggregate values into reports unless they are loaded from a machine-readable result artifact.

## 11. Revised Claim Ladder

### Primary claim

The system detects response omissions by comparing linked answer members with scope-bounded certain answers computed from a versioned institutional KG, improving omission detection over claim-only verification and LLM-as-judge baselines.

### Secondary claim

Separate, calibrated omission-risk and false-contradiction-risk gates expose a tunable automation frontier that institutions can configure under explicit cost and risk budgets.

### Supporting claim

Audited relation-completeness certificates improve interpretation of absent facts compared with fixed CWA/OWA and raw relation occupancy.

### Validation-method claim

Paired graph-destruction controls reveal whether a claimed KG verifier actually depends on graph content after decomposition and linking are held fixed.

Avoid claiming that completeness-triggered abstention is entirely unprecedented. PassiveQA explicitly routes on incomplete information and missing variables. The defensible distinction is post-hoc verification of the generated answer's set recall against authoritative KG-derived expected answers, followed by risk-controlled deferral.

## 12. Literature Positioning After Web Check

- **Beyond Precision** (Jafari et al., arXiv:2604.03141, 2026) directly supports the factual-recall gap, but concerns open-ended long-form generation rather than institutional KG certain answers.
- **Same Verdict, Different Reasons** (DeLucia et al., arXiv:2604.16383, 2026) reports weak LLM-judge discrimination for medical response completeness, motivating deterministic expected-set evidence.
- **Fact Finder** (Steinigen et al., arXiv:2408.03010, 2024) evaluates KG-augmented medical answers for accuracy and completeness with an LLM judge. It is a required baseline/closest-work citation, but does not provide deterministic set-recall verification or calibrated deferral.
- **Mitigating LLM Hallucinations via Conformal Abstention** (Yadkori et al., arXiv:2405.01563, 2024) provides conformal abstention for hallucination/error risk using response consistency, not KG-derived omission risk.
- **PassiveQA** (Baidya, arXiv:2604.04565, 2026) uses known/missing variables and KG context for `Answer`/`Ask`/`Abstain`. It narrows the novelty claim: this work must distinguish response-set completeness from query answerability and missing user variables.
- **Two Axes of LLM Abstention** (Wagner, arXiv:2607.08456, 2026) shows that correctness and answerability need separate scores and risk budgets. This strongly supports a dual-risk controller rather than one multiplied confidence score.

The literature search should be documented as a reproducible protocol before submission: databases, search strings, date range, inclusion criteria, and a closest-work comparison table.

## 13. Delivery Sequence

### Milestone 0: Stop invalid evidence propagation, 1-2 days

- Mark current headline reports and result tables as provisional.
- Create an experiment registry listing script, data, graph, model, and status: measured, simulated, synthetic fallback, or invalidated.
- Select one authoritative entry point for each experiment.

### Milestone 1: Correct evaluation substrate, 3-5 days

- Remove the global store bug.
- Make verification context local and concurrency-safe.
- Add deterministic unit tests and row-level run manifests.
- Rebuild the paired shuffled-KG control without LLM reruns between conditions.

### Milestone 2: Build the actual advising benchmark, 2-4 weeks

- Expand and version both institutional graphs.
- Implement deterministic expected-set queries.
- Create student/program contexts and partial-answer perturbations.
- Complete advisor audit and freeze splits.

### Milestone 3: Implement answer completeness, 1-2 weeks

- Add `QuerySpec`, expected-set computation, answer-member extraction, set matching, and structured provenance.
- Preserve correctness and completeness as separate outputs.

### Milestone 4: Implement and calibrate dual-risk deferral, 1-2 weeks

- Collect real score-label pairs.
- Fit transparent calibration models on the calibration split.
- Generate measured risk-coverage-cost curves and risk bounds.

### Milestone 5: Run the preregistered experiment matrix, 2-3 weeks

- Run E1-E8 with frozen code/data.
- Run the advisor pilot only after offline gates pass.
- Generate all tables and figures directly from immutable artifacts.

## 14. Go/No-Go Gates for the Paper

Do not make the headline claims until all gates pass:

1. Independent graph stores and deterministic cached-condition evaluations are verified by tests.
2. Every reported metric can be reconstructed from row-level predictions.
3. The institutional benchmark contains real set-valued advising queries with audited expected sets.
4. The completeness method beats claim-only and LLM-judge baselines on omission detection with a meaningful paired effect.
5. At least one nontrivial threshold meets a preregistered omission-risk bound at useful automation coverage.
6. Relation completeness estimates have source evidence and uncertainty, not only occupancy.
7. Shuffled-KG controls use paired baselines and repeated valid derangements.
8. Claims, code, artifacts, and report tables agree.

If Gate 4 fails, the paper can still become a useful negative result about linking and expected-set extraction. If Gate 5 fails, present abstention as an empirical operating curve without a formal risk guarantee. If the audited KG is not complete enough for Gate 6, narrow the task to relations with explicit institutional completeness guarantees.
