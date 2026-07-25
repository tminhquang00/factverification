import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_advisor_audit_packet import generate_audit_packet


class AdvisorAuditPacketTests(unittest.TestCase):
    def test_packet_links_source_and_leaves_review_fields_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            graph_path = temp_path / "graph.json"
            source_dir = temp_path / "sources"
            output_path = temp_path / "audit.csv"
            manifest_path = temp_path / "manifest.json"
            source_dir.mkdir()
            graph_path.write_text(
                json.dumps(
                    {
                        "123456": {
                            "title": "Target Course",
                            "prerequisites": [
                                {"course_id": "111111", "title": "First"},
                                {"course_id": "222222", "title": "Second"},
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            source_file = source_dir / "123456_Target Course.html"
            source_file.write_text("<html>source</html>", encoding="utf-8")

            manifest = generate_audit_packet(
                str(graph_path),
                str(source_dir),
                str(output_path),
                str(manifest_path),
            )
            with output_path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

            self.assertEqual(manifest["course_count"], 1)
            self.assertEqual(manifest["source_file_matches"], 1)
            self.assertEqual(row["expected_prerequisite_ids"], "111111|222222")
            self.assertEqual(row["expected_set_status"], "")
            self.assertTrue(row["source_file"].endswith("123456_Target Course.html"))