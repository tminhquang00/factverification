import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


REQUIRED_REVIEW_FIELDS = [
    "source_accessible",
    "query_scope_valid",
    "expected_set_status",
    "reviewer_confidence",
    "reviewer_id",
    "review_date",
]
ALLOWED_VALUES = {
    "source_accessible": {"yes", "no"},
    "query_scope_valid": {"yes", "no", "uncertain"},
    "expected_set_status": {"correct", "missing_items", "extra_items", "uncertain"},
    "reviewer_confidence": {"high", "medium", "low"},
}


def _is_review_started(row):
    return any(str(row.get(field, "")).strip() for field in REQUIRED_REVIEW_FIELDS)


def validate_audit(input_path: str, output_path: str):
    with Path(input_path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    validation_errors = []
    reviewed_rows = []
    for row_number, row in enumerate(rows, start=2):
        if not _is_review_started(row):
            continue
        reviewed_rows.append(row)
        for field in REQUIRED_REVIEW_FIELDS:
            if not str(row.get(field, "")).strip():
                validation_errors.append(f"row {row_number}: missing {field}")
        for field, allowed in ALLOWED_VALUES.items():
            value = str(row.get(field, "")).strip().lower()
            if value and value not in allowed:
                validation_errors.append(f"row {row_number}: invalid {field}={value}")
        status = str(row.get("expected_set_status", "")).strip().lower()
        corrected = str(row.get("corrected_prerequisite_ids", "")).strip()
        if status in {"missing_items", "extra_items"} and not corrected:
            validation_errors.append(
                f"row {row_number}: corrected_prerequisite_ids required for {status}"
            )
        review_date = str(row.get("review_date", "")).strip()
        if review_date:
            try:
                date.fromisoformat(review_date)
            except ValueError:
                validation_errors.append(f"row {row_number}: invalid ISO review_date={review_date}")

    required_rows = [row for row in rows if row.get("benchmark_split") in {"calibration", "test"}]
    reviewed_ids = {row["course_id"] for row in reviewed_rows}
    required_reviewed = sum(row["course_id"] in reviewed_ids for row in required_rows)
    if validation_errors:
        status = "invalid_review_data"
    elif required_reviewed == len(required_rows):
        status = "ready_for_dataset_revision"
    else:
        status = "awaiting_review"

    status_counts = Counter(
        str(row.get("expected_set_status", "")).strip().lower()
        for row in reviewed_rows
        if str(row.get("expected_set_status", "")).strip()
    )
    confidence_counts = Counter(
        str(row.get("reviewer_confidence", "")).strip().lower()
        for row in reviewed_rows
        if str(row.get("reviewer_confidence", "")).strip()
    )
    summary = {
        "schema_version": 1,
        "audit_packet": input_path,
        "status": status,
        "total_courses": len(rows),
        "reviewed_courses": len(reviewed_rows),
        "required_calibration_test_courses": len(required_rows),
        "reviewed_required_courses": required_reviewed,
        "remaining_required_courses": len(required_rows) - required_reviewed,
        "expected_set_status_counts": dict(sorted(status_counts.items())),
        "reviewer_confidence_counts": dict(sorted(confidence_counts.items())),
        "validation_errors": validation_errors,
        "single_reviewer_design": True,
        "inter_annotator_agreement_available": False,
    }
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Validate and summarize the RMIT expert audit CSV.")
    parser.add_argument("--input", default="data/advising/rmit_prerequisite_expected_set_audit_v0.csv")
    parser.add_argument("--output", default="data/advising/rmit_prerequisite_expected_set_audit_v0.summary.json")
    args = parser.parse_args()
    summary = validate_audit(args.input, args.output)
    print(json.dumps(summary, indent=2))
    return 1 if summary["status"] == "invalid_review_data" else 0


if __name__ == "__main__":
    raise SystemExit(main())