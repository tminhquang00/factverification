import unittest

from abstention_controller import (
    CalibratedRisk,
    DualRiskAssessment,
    DualRiskController,
    VerificationAction,
)


class DualRiskControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = DualRiskController(
            wrong_answer_budget=0.05,
            omission_budget=0.10,
        )

    def test_accepts_only_when_both_risks_are_within_budget(self):
        decision = self.controller.decide(
            DualRiskAssessment(
                wrong_answer=CalibratedRisk(0.04, "cal-v1"),
                omission=CalibratedRisk(0.08, "cal-v1"),
            )
        )

        self.assertEqual(decision.action, VerificationAction.ACCEPT)
        self.assertEqual(decision.violated_budgets, tuple())

    def test_omission_budget_can_trigger_deferral_independently(self):
        decision = self.controller.decide(
            DualRiskAssessment(
                wrong_answer=CalibratedRisk(0.01, "cal-v1"),
                omission=CalibratedRisk(0.11, "cal-v1"),
            )
        )

        self.assertEqual(decision.action, VerificationAction.DEFER)
        self.assertEqual(decision.violated_budgets, ("omission",))

    def test_recoverable_budget_violation_routes_to_revision(self):
        decision = self.controller.decide(
            DualRiskAssessment(
                wrong_answer=CalibratedRisk(0.20, "cal-v1"),
                omission=CalibratedRisk(0.30, "cal-v1"),
            ),
            recoverable=True,
        )

        self.assertEqual(decision.action, VerificationAction.REVISE)
        self.assertEqual(decision.violated_budgets, ("wrong_answer", "omission"))

    def test_uncalibrated_scores_never_accept(self):
        decision = self.controller.decide(
            DualRiskAssessment(
                wrong_answer=CalibratedRisk(0.01, "none", calibrated=False),
                omission=CalibratedRisk(0.01, "cal-v1"),
            )
        )

        self.assertEqual(decision.action, VerificationAction.DEFER)
        self.assertEqual(decision.violated_budgets, ("wrong_answer",))


if __name__ == "__main__":
    unittest.main()