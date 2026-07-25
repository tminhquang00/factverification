import unittest
from collections import Counter

from scripts.run_graph_destruction_control import (
    _clustered_accuracy_drop_ci,
    destroy_prerequisite_graph,
)


class GraphDestructionControlTests(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "A": {"prerequisites": [{"course_id": "X"}, {"course_id": "Y"}]},
            "B": {"prerequisites": [{"course_id": "Z"}, {"course_id": "W"}]},
        }

    def _objects(self, graph):
        return [
            item["course_id"]
            for subject in sorted(graph)
            for item in graph[subject]["prerequisites"]
        ]

    def test_shuffle_preserves_multiset_and_changes_every_edge(self):
        shuffled = destroy_prerequisite_graph(self.graph, condition="shuffled", seed=42)

        original_objects = self._objects(self.graph)
        shuffled_objects = self._objects(shuffled)
        self.assertEqual(Counter(original_objects), Counter(shuffled_objects))
        self.assertTrue(all(left != right for left, right in zip(original_objects, shuffled_objects)))
        self.assertEqual(self._objects(self.graph), ["X", "Y", "Z", "W"])

    def test_empty_condition_removes_only_prerequisite_edges(self):
        graph = {
            "A": {
                "credits": 12,
                "prerequisites": [{"course_id": "X"}],
            }
        }

        empty = destroy_prerequisite_graph(graph, condition="empty")

        self.assertEqual(empty["A"]["prerequisites"], [])
        self.assertEqual(empty["A"]["credits"], 12)

    def test_clustered_drop_is_paired_by_subject(self):
        baseline_rows = [
            {"id": "a-1", "subject_id": "A", "predicted_completeness": "complete", "gold_completeness": "complete"},
            {"id": "a-2", "subject_id": "A", "predicted_completeness": "incomplete", "gold_completeness": "incomplete"},
            {"id": "b-1", "subject_id": "B", "predicted_completeness": "complete", "gold_completeness": "complete"},
        ]
        condition_rows = [
            {"id": "a-1", "subject_id": "A", "predicted_completeness": "incomplete", "gold_completeness": "complete"},
            {"id": "a-2", "subject_id": "A", "predicted_completeness": "complete", "gold_completeness": "incomplete"},
            {"id": "b-1", "subject_id": "B", "predicted_completeness": "complete", "gold_completeness": "complete"},
        ]

        result = _clustered_accuracy_drop_ci(
            baseline_rows,
            condition_rows,
            seed=42,
            resamples=100,
        )

        self.assertGreater(result["clustered_bootstrap_mean_accuracy_drop"], 0.0)
        self.assertEqual(result["cluster_unit"], "subject_id")
        self.assertEqual(result["bootstrap_resamples"], 100)