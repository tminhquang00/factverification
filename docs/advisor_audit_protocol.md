# RMIT Prerequisite Expected-Set Audit Protocol

## Purpose

This audit checks whether each KG-derived prerequisite answer set accurately reflects the cited RMIT handbook source. It does not evaluate generated LLM responses and does not ask the reviewer to judge system fluency.

The current design has one expert reviewer. Results may support an expert source-audit claim, but not inter-annotator agreement or adjudication claims.

## Audit Packet

Use [`../data/advising/rmit_prerequisite_expected_set_audit_v0.csv`](../data/advising/rmit_prerequisite_expected_set_audit_v0.csv). Each row represents one course and includes:

* The set-valued advising query.
* KG-derived prerequisite IDs and titles.
* A cached handbook HTML source and live handbook URL.
* Empty reviewer fields.

Review `test` rows first, followed by `calibration`, then `development`. Do not modify query text, expected-set fields, source references, course IDs, or split assignments.

## Review Procedure

1. Open the cached `source_file`. Use `source_url` if the cached record is unreadable or appears stale.
2. Locate the course's prerequisite or prior-knowledge section.
3. Decide whether the query “Which course IDs are listed in the prerequisite section for this course?” has a well-defined answer from that source.
4. Compare every source-listed course prerequisite with `expected_prerequisite_ids`.
5. Preserve AND/OR structure in `reviewer_notes`; the v0 benchmark evaluates listed-course membership and does not yet evaluate eligibility or Boolean prerequisite alternatives.
6. Complete every reviewer field using the allowed values below.

## Allowed Values

`source_accessible`:

* `yes`
* `no`

`query_scope_valid`:

* `yes`: the source defines a course-prerequisite set for this query.
* `no`: the source uses non-course conditions, alternatives that cannot be represented as a set, or another scope problem.
* `uncertain`

`expected_set_status`:

* `correct`: the IDs exactly match all course prerequisites in source.
* `missing_items`: one or more source prerequisites are absent from the KG set.
* `extra_items`: one or more KG items are not prerequisites in source.
* `uncertain`: the source cannot support a definitive set judgment.

`corrected_prerequisite_ids`:

* Enter the complete corrected set using `|` between IDs when status is `missing_items` or `extra_items`.
* Enter an empty string only when the corrected set is empty.
* Leave blank for `correct` or `uncertain`.

`reviewer_confidence`:

* `high`
* `medium`
* `low`

Also complete `reviewer_notes`, `reviewer_id`, and `review_date` in ISO format (`YYYY-MM-DD`).

## Acceptance Gate

Before the dataset is promoted beyond candidate status:

* Every test and calibration row must be reviewed.
* No reviewed row may have missing reviewer fields.
* Rows marked `query_scope_valid=no` or `uncertain` must be excluded from efficacy evaluation or moved to an explicit indeterminate-scope analysis.
* All corrections must be applied to a new graph/dataset version; never edit the current candidate artifact in place.
* The audit summary must report reviewed count, source accessibility, exact-set acceptance rate, correction count, exclusions, and reviewer-confidence distribution.

Run the validator after each review batch:

```powershell
& .venv\Scripts\python.exe scripts\validate_advisor_audit.py
```

The packet is not ready for dataset revision until the summary status is `ready_for_dataset_revision`.
