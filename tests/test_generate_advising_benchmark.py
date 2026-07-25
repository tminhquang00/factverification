import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_advising_benchmark import generate_benchmark


class AdvisingBenchmarkGenerationTests(unittest.TestCase):
    def test_generation_is_grouped_by_subject_and_records_gold_sets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            graph_path = temp_path / "graph.json"
            output_path = temp_path / "benchmark.jsonl"
            manifest_path = temp_path / "manifest.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "100000": {
                            "prerequisites": [
                                {"course_id": "111111"},
                                {"course_id": "222222"},
                            ]
                        },
                        "111111": {"prerequisites": []},
                        "222222": {"prerequisites": []},
                        "333333": {"prerequisites": []},
                    }
                ),
                encoding="utf-8",
            )

            manifest = generate_benchmark(
                str(graph_path),
                str(output_path),
                str(manifest_path),
            )
            records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            target_records = [record for record in records if record["query_spec"]["subject_id"] == "100000"]

            self.assertEqual(manifest["subject_count"], 4)
            self.assertEqual(len({record["split"] for record in target_records}), 1)
            self.assertEqual(
                {record["response_condition"] for record in target_records},
                {
                    "complete_correct",
                    "complete_plus_distractor",
                    "omit_one",
                    "omit_multiple",
                    "corrupted_member",
                },
            )
            omit_one = next(record for record in target_records if record["response_condition"] == "omit_one")
            self.assertEqual(omit_one["gold_completeness"], "incomplete")
            self.assertEqual(len(omit_one["gold_missing"]), 1)
            self.assertEqual(omit_one["gold_set_recall"], 0.5)
            self.assertTrue(manifest["kg_version"].startswith("sha256:"))