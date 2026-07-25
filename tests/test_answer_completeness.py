import json
import tempfile
import unittest
from pathlib import Path

from answer_completeness import (
    AnswerCompletenessVerifier,
    CompletenessVerdict,
    QueryIntent,
    QuerySpec,
    parse_query_spec,
)
from kg_store import get_kg_store


class AnswerCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        graph_path = Path(self.temp_dir.name) / "graph.json"
        graph_path.write_text(
            json.dumps(
                {
                    "123456": {
                        "title": "Target",
                        "prerequisites": [
                            {"course_id": "111111"},
                            {"course_id": "222222"},
                        ],
                    },
                    "654321": {"title": "No prerequisites", "prerequisites": []},
                }
            ),
            encoding="utf-8",
        )
        self.verifier = AnswerCompletenessVerifier(get_kg_store(str(graph_path)))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detects_an_omitted_prerequisite(self):
        spec = QuerySpec(QueryIntent.ALL_PREREQUISITES, "123456", "test-v1")

        result = self.verifier.verify(spec, "Course 123456 requires 111111.")

        self.assertEqual(result.verdict, CompletenessVerdict.INCOMPLETE)
        self.assertEqual(result.missing, frozenset({"222222"}))
        self.assertEqual(result.set_precision, 1.0)
        self.assertEqual(result.set_recall, 0.5)
        self.assertFalse(result.exact_set_match)

    def test_separates_completeness_from_unexpected_members(self):
        spec = QuerySpec(QueryIntent.ALL_PREREQUISITES, "123456", "test-v1")

        result = self.verifier.verify(
            spec,
            "The prerequisites are 111111, 222222, and 333333.",
        )

        self.assertEqual(result.verdict, CompletenessVerdict.COMPLETE)
        self.assertEqual(result.missing, frozenset())
        self.assertEqual(result.unexpected, frozenset({"333333"}))
        self.assertAlmostEqual(result.set_precision, 2 / 3)
        self.assertEqual(result.set_recall, 1.0)
        self.assertFalse(result.exact_set_match)

    def test_empty_expected_and_mentioned_sets_are_complete(self):
        spec = QuerySpec(QueryIntent.ALL_PREREQUISITES, "654321", "test-v1")

        result = self.verifier.verify(spec, "Course 654321 has no prerequisites.")

        self.assertEqual(result.verdict, CompletenessVerdict.COMPLETE)
        self.assertEqual(result.set_precision, 1.0)
        self.assertEqual(result.set_recall, 1.0)
        self.assertTrue(result.exact_set_match)

    def test_unknown_subject_is_indeterminate(self):
        spec = QuerySpec(QueryIntent.ALL_PREREQUISITES, "999999", "test-v1")

        result = self.verifier.verify(spec, "Course 999999 requires 111111.")

        self.assertEqual(result.verdict, CompletenessVerdict.INDETERMINATE)
        self.assertIsNone(result.set_recall)

    def test_parses_prerequisite_query_scope(self):
        spec = parse_query_spec("What are all prerequisites for 123456?", "test-v1")

        self.assertIsNotNone(spec)
        self.assertEqual(spec.intent, QueryIntent.ALL_PREREQUISITES)
        self.assertEqual(spec.subject_id, "123456")