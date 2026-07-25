import unittest

from eval_harness import compute_metrics


class CrashScoringTests(unittest.TestCase):
    """A crash must not be scored as a prediction.

    The harness previously substituted the dataset default label on any exception. On FactKG
    that default (`Contradicted`) is also the majority class, so 113 stage-3 crashes were
    scored as 111 correct predictions and the run reported 81.4% accuracy. Unscored rows are
    now represented by a `None` prediction and excluded from the denominator.
    """

    def test_unscored_rows_are_excluded_from_the_denominator(self):
        # Two correct predictions, two crashes whose gold happens to be the default label.
        predictions = ["Supported", "Contradicted", None, None]
        golds = ["Supported", "Contradicted", "Contradicted", "Contradicted"]

        accuracy, _, _, _, n_scored = compute_metrics(predictions, golds)

        self.assertEqual(n_scored, 2)
        self.assertEqual(accuracy, 1.0)

    def test_crashes_cannot_inflate_accuracy(self):
        """The same crashes, had they been defaulted to the majority class, would score 100%."""
        crashed = ["Supported", None, None, None]
        golds = ["Supported", "Contradicted", "Contradicted", "Contradicted"]
        defaulted = ["Supported", "Contradicted", "Contradicted", "Contradicted"]

        honest_accuracy, _, _, _, n_scored = compute_metrics(crashed, golds)
        inflated_accuracy, _, _, _, _ = compute_metrics(defaulted, golds)

        self.assertEqual(n_scored, 1)
        self.assertEqual(honest_accuracy, 1.0)
        self.assertEqual(inflated_accuracy, 1.0)
        # The honest run reports its accuracy over 1 row, not 4 — the caller can see the gap.
        self.assertLess(n_scored, len(golds))

    def test_per_class_support_ignores_unscored_rows(self):
        predictions = [None, "Supported", "Contradicted"]
        golds = ["Not-in-KG", "Supported", "Contradicted"]

        _, rows, _, _, n_scored = compute_metrics(predictions, golds)
        support = {row[0]: row[4] for row in rows}

        self.assertEqual(n_scored, 2)
        self.assertEqual(support["Not-in-KG"], 0)

    def test_all_rows_unscored_yields_zero_accuracy_not_a_crash(self):
        accuracy, _, lower, upper, n_scored = compute_metrics([None, None], ["Supported", "Supported"])

        self.assertEqual(n_scored, 0)
        self.assertEqual(accuracy, 0)
        self.assertEqual((lower, upper), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
