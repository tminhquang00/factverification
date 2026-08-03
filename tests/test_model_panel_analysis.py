"""Tests for the multi-vendor panel analysis.

The panel's headline safety metric can be gamed: a model that answers "Not-in-KG" to everything
scores a contradiction rate on true claims of exactly zero while being useless. The abstention
precision/recall pair exists to make that visible, and these tests pin that behaviour so the
distinction cannot silently disappear.
"""

import unittest

from scripts.analyze_model_panel import spearman, summarize_cell


def row(prediction, gold, world_truth, question_id="q1"):
    return {
        "prediction": prediction,
        "gold": gold,
        "world_truth": world_truth,
        "question_id": question_id,
    }


class AbstentionQualityTests(unittest.TestCase):
    def test_indiscriminate_abstainer_is_exposed_by_low_precision(self):
        """Zero harm plus poor abstention precision is the signature of a useless model."""
        rows = [
            row("Not-in-KG", "Supported", "true", "q1"),
            row("Not-in-KG", "Supported", "true", "q2"),
            row("Not-in-KG", "Not-in-KG", "true", "q3"),
            row("Not-in-KG", "Contradicted", "false", "q4"),
        ]
        summary = summarize_cell(rows, "prediction", iterations=50, seed=1)
        self.assertEqual(summary["contradiction_rate_on_true_claims"], 0.0)
        self.assertAlmostEqual(summary["abstention_precision"], 0.25)
        self.assertEqual(summary["abstention_recall"], 1.0)
        self.assertEqual(summary["accuracy"], 0.25)

    def test_calibrated_abstainer_scores_high_on_both(self):
        rows = [
            row("Not-in-KG", "Not-in-KG", "true", "q1"),
            row("Not-in-KG", "Not-in-KG", "false", "q2"),
            row("Supported", "Supported", "true", "q3"),
            row("Contradicted", "Contradicted", "false", "q4"),
        ]
        summary = summarize_cell(rows, "prediction", iterations=50, seed=1)
        self.assertEqual(summary["abstention_precision"], 1.0)
        self.assertEqual(summary["abstention_recall"], 1.0)
        self.assertEqual(summary["contradiction_rate_on_true_claims"], 0.0)
        self.assertEqual(summary["accuracy"], 1.0)

    def test_under_abstention_shows_up_as_harm_with_intact_precision(self):
        """The panel's actual failure mode: precision stays 1.0, recall collapses."""
        rows = [
            row("Contradicted", "Not-in-KG", "true", "q1"),
            row("Contradicted", "Not-in-KG", "true", "q2"),
            row("Not-in-KG", "Not-in-KG", "true", "q3"),
        ]
        summary = summarize_cell(rows, "prediction", iterations=50, seed=1)
        self.assertAlmostEqual(summary["contradiction_rate_on_true_claims"], 2 / 3)
        self.assertEqual(summary["abstention_precision"], 1.0)
        self.assertAlmostEqual(summary["abstention_recall"], 1 / 3)

    def test_true_world_metric_ignores_non_true_claims(self):
        rows = [
            row("Contradicted", "Contradicted", "false", "q1"),
            row("Contradicted", "Not-in-KG", "unknown", "q2"),
            row("Supported", "Supported", "true", "q3"),
        ]
        summary = summarize_cell(rows, "prediction", iterations=50, seed=1)
        self.assertEqual(summary["n_true_world_claims"], 1)
        self.assertEqual(summary["contradiction_rate_on_true_claims"], 0.0)

    def test_empty_cell_is_reported_rather_than_crashing(self):
        self.assertEqual(summarize_cell([], "prediction", iterations=10, seed=1), {"n_rows": 0})

    def test_rows_without_a_prediction_are_excluded_not_counted_wrong(self):
        rows = [row("Supported", "Supported", "true", "q1"), row(None, "Supported", "true", "q2")]
        summary = summarize_cell(rows, "prediction", iterations=50, seed=1)
        self.assertEqual(summary["n_rows"], 1)
        self.assertEqual(summary["accuracy"], 1.0)

    def test_bootstrap_interval_brackets_the_point_estimate(self):
        rows = [row("Contradicted", "Not-in-KG", "true", f"q{i}") for i in range(10)]
        rows += [row("Not-in-KG", "Not-in-KG", "true", f"r{i}") for i in range(10)]
        summary = summarize_cell(rows, "prediction", iterations=500, seed=7)
        low, high = summary["contradiction_rate_on_true_claims_ci95"]
        self.assertLessEqual(low, summary["contradiction_rate_on_true_claims"])
        self.assertGreaterEqual(high, summary["contradiction_rate_on_true_claims"])


class SpearmanTests(unittest.TestCase):
    def test_perfect_negative_rank_correlation(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_perfect_positive_rank_correlation(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)

    def test_none_values_are_dropped_pairwise(self):
        self.assertAlmostEqual(spearman([1, 2, None, 4], [4, 3, 2, 1]), -1.0)

    def test_returns_none_when_there_is_too_little_data(self):
        self.assertIsNone(spearman([1, 2], [2, 1]))

    def test_returns_none_when_a_series_is_constant(self):
        self.assertIsNone(spearman([1, 1, 1, 1], [1, 2, 3, 4]))

    def test_handles_ties_without_crashing(self):
        value = spearman([1, 1, 2, 3], [1, 2, 2, 3])
        self.assertIsNotNone(value)
        self.assertGreater(value, 0)


if __name__ == "__main__":
    unittest.main()
