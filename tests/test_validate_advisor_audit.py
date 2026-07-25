import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_advisor_audit_packet import FIELDNAMES
from scripts.validate_advisor_audit import validate_audit


class AdvisorAuditValidationTests(unittest.TestCase):
    def _write_rows(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    def test_unreviewed_packet_remains_awaiting_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "audit.csv"
            output_path = temp_path / "summary.json"
            self._write_rows(
                input_path,
                [{field: "" for field in FIELDNAMES} | {"course_id": "A", "benchmark_split": "test"}],
            )

            summary = validate_audit(str(input_path), str(output_path))

            self.assertEqual(summary["status"], "awaiting_review")
            self.assertEqual(summary["remaining_required_courses"], 1)

    def test_complete_required_review_is_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "audit.csv"
            output_path = temp_path / "summary.json"
            row = {field: "" for field in FIELDNAMES}
            row.update(
                {
                    "course_id": "A",
                    "benchmark_split": "calibration",
                    "source_accessible": "yes",
                    "query_scope_valid": "yes",
                    "expected_set_status": "correct",
                    "reviewer_confidence": "high",
                    "reviewer_id": "reviewer-1",
                    "review_date": "2026-07-25",
                }
            )
            self._write_rows(input_path, [row])

            summary = validate_audit(str(input_path), str(output_path))

            self.assertEqual(summary["status"], "ready_for_dataset_revision")
            self.assertEqual(summary["validation_errors"], [])

    def test_partial_or_invalid_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "audit.csv"
            output_path = temp_path / "summary.json"
            row = {field: "" for field in FIELDNAMES}
            row.update(
                {
                    "course_id": "A",
                    "benchmark_split": "test",
                    "source_accessible": "maybe",
                    "expected_set_status": "missing_items",
                    "reviewer_id": "reviewer-1",
                    "review_date": "25/07/2026",
                }
            )
            self._write_rows(input_path, [row])

            summary = validate_audit(str(input_path), str(output_path))

            self.assertEqual(summary["status"], "invalid_review_data")
            self.assertGreater(len(summary["validation_errors"]), 1)