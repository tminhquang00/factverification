# Data and Benchmark Construction

**Updated:** 2026-08-03
**Current artifacts:** NUSMods 200-question study and RMIT 50-question transfer study

This is the construction record for the current experiment. Older synthetic-claim benchmarks and
dated pilot sets are not sources for the final study.

## 1. Source graphs

### NUSMods

`scripts/parse_nusmods.py` compiles cached NUSMods module records into
`data/nusmods_graph.json`. The fixed snapshot contains 11,647 module entities spanning the cached
academic-year records. `data/nusmods_snapshot.manifest.json` records the source files, timestamps,
counts, parser hash, and compiled graph SHA-256.

Each module can contain:

- course code and title;
- numeric credit value;
- school/faculty;
- prerequisite course codes;
- preclusion course codes;
- offered semesters;
- optional staffing fields.

The parser writes explicit empty lists for catalog-complete set relations. This is essential:
“no prerequisites” must remain distinguishable from “prerequisite information unavailable.”

`data/completeness_declarations/nusmods.json` declares catalog relations complete in the fixed full
snapshot and staffing (`taughtBy`) incomplete. This is a researcher declaration based on catalog
semantics, not a declaration supplied by NUS.

### RMIT

`data/rmit_graph.json` contains 50 handbook-derived course entities. The current experiment uses
the normalized graph fields and `data/completeness_declarations/rmit.json`. RMIT is a small schema
and language transfer check; it is not the primary statistical testbed.

### Public graphs

FactKG is evaluated from per-claim context triples. CoDEx uses an open-domain graph whose entity
keys and relation values occupy different namespaces. Their declaration files live beside the
institutional declarations. Public benchmarks assess pipeline portability and sampling sensitivity,
not the controlled-deletion hypothesis.

## 2. Question construction

### NUSMods 200-question set

`scripts/generate_nusmods_questions.py` creates
`data/nusmods_questions_200.jsonl` deterministically. The set has 200 questions and 300 distinct
expected triples.

| Question type | Questions |
| --- | ---: |
| Preclusion existence | 25 |
| Conjunction | 25 |
| Scalar credit | 24 |
| Offered-term membership | 24 |
| Prerequisite existence | 24 |
| Staffing open-world anchor | 24 |
| Prerequisite exhaustiveness | 18 |
| Prerequisite multi-hop | 18 |
| Mixed fact and advice | 18 |

Expected-triple composition is 124 prerequisite, 67 credit, 36 preclusion, 25 school, 24 semester,
and 24 staffing triples. Staffing anchors natural missingness; because the graph does not claim a
staff member, those triples are excluded from expected-fact extraction recall where appropriate and
retained in open-world verification diagnostics.

The companion manifest records the seed, generator hash, graph hash, relation/type counts, and file
hash. Questions and expected triples are graph-derived; they are not human annotated.

### RMIT 50-question set

`scripts/generate_rmit_questions.py` creates `data/rmit_questions_50.jsonl`: 50 questions and 66
distinct expected triples.

| Question type | Questions |
| --- | ---: |
| Prerequisite existence | 10 |
| Scalar credit | 8 |
| School lookup | 8 |
| Conjunction | 8 |
| Coordinator lookup | 8 |
| Prerequisite multi-hop | 4 |
| Mixed fact and advice | 4 |

The RMIT generator writes a manifest with the same provenance fields as the NUSMods set.

## 3. Answer generation

Each question is answered under three conditions:

| Condition | Evidence supplied to the answer generator |
| --- | --- |
| `closed_book` | Question only. |
| `rag_full` | Relation-specific records from the full graph. |
| `rag_degraded` | The same construction against a 50%-retention graph. |

“RAG” here means graph-record context assembled from the question’s known subject and relation. It
does not include a learned retriever. This makes the answer-generation comparison controlled but
must not be described as end-to-end retrieval performance.

The hosted arm uses `azure-4.1-mini`; the local arm uses `google/gemma-4-e4b` through LM Studio’s
OpenAI-compatible endpoint. Answer temperature is `0.2`. Generator and detector identities are
recorded separately so self-detector and cross-detector arms can reuse exactly the same answers.

## 4. Controlled graph degradation

`scripts/build_degraded_graphs.py` removes facts while preserving every entity node.

Degraded relations are:

- `hasCreditValue`;
- `partOfSchool`;
- `requiresPrerequisite`;
- `preclusions`;
- `offeredInTerm`.

NUSMods uses nominal retention `100/95/90/80/50/20%`; RMIT uses `100/50/20%`. Three seeds
(`20260802`, `20260803`, `20260804`) and two modes are built.

- Random mode samples individual relation facts and meets the requested count up to rounding.
- Clustered mode removes department groups. Its realized relation-level retention can depart from
  the target because departments have different sizes.

For example, “80% retention” means approximately 80% of facts in each listed relation remain. It
does not mean 80% of questions, answers, modules, decomposition agreement, or accuracy.

Every condition directory contains the degraded graph, a deleted-triple JSONL log, a companion
completeness declaration, and a manifest with requested/realized retention and hashes.

## 5. Mechanical gold

Gold is recomputed during rescoring rather than copied from a saved model run.

| Full-world fact | Condition graph | Relation status | Gold |
| --- | --- | --- | --- |
| True | Present | any | `Supported` |
| True | Deleted/absent | incomplete | `Not-in-KG` |
| False with incompatible value present | any | any | `Contradicted` |
| False and absent | complete | `Contradicted` |
| False and absent | incomplete | `Not-in-KG` |

String normalization handles organizational prefixes, person punctuation, course-code objects, and
numeric strings. This gold is independent of the saved Stage 4 prediction, but it still shares the
researcher-authored graph/declaration semantics and has no human validation in the present study.

## 6. Artifact locations

- Question and graph inputs: `data/`
- Degraded NUSMods graphs: `output/experiments/nusmods_degradation_final/`
- Degraded RMIT graphs: `output/experiments/rmit_degradation_final/`
- Final row-level study artifacts: `output/experiments/incompleteness_final_20260803/`
- Public transfer artifacts: `output/experiments/final_public_20260803_azure/` and the corresponding
  local run directory

The current status page and final report identify which exact files are citable.
