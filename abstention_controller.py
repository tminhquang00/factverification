from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Tuple


class VerificationAction(str, Enum):
    ACCEPT = "accept"
    REVISE = "revise"
    DEFER = "defer"


@dataclass(frozen=True)
class CalibratedRisk:
    value: float
    calibration_id: str
    calibrated: bool = True

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError("Risk values must be between 0 and 1.")


@dataclass(frozen=True)
class DualRiskAssessment:
    wrong_answer: CalibratedRisk
    omission: CalibratedRisk


@dataclass(frozen=True)
class ActionDecision:
    action: VerificationAction
    violated_budgets: Tuple[str, ...]
    reason: str
    wrong_answer_budget: float
    omission_budget: float
    assessment: DualRiskAssessment

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


class DualRiskController:
    """Applies independent institution-selected budgets to calibrated risks."""

    def __init__(self, wrong_answer_budget: float, omission_budget: float):
        for name, value in {
            "wrong_answer_budget": wrong_answer_budget,
            "omission_budget": omission_budget,
        }.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")
        self.wrong_answer_budget = wrong_answer_budget
        self.omission_budget = omission_budget

    def decide(self, assessment: DualRiskAssessment, recoverable: bool = False) -> ActionDecision:
        risks = {
            "wrong_answer": assessment.wrong_answer,
            "omission": assessment.omission,
        }
        uncalibrated = tuple(name for name, risk in risks.items() if not risk.calibrated)
        if uncalibrated:
            return ActionDecision(
                action=VerificationAction.DEFER,
                violated_budgets=uncalibrated,
                reason="Risk estimates are not calibrated for this deployment domain.",
                wrong_answer_budget=self.wrong_answer_budget,
                omission_budget=self.omission_budget,
                assessment=assessment,
            )

        violated = []
        if assessment.wrong_answer.value > self.wrong_answer_budget:
            violated.append("wrong_answer")
        if assessment.omission.value > self.omission_budget:
            violated.append("omission")

        if not violated:
            return ActionDecision(
                action=VerificationAction.ACCEPT,
                violated_budgets=tuple(),
                reason="Both calibrated risks are within their configured budgets.",
                wrong_answer_budget=self.wrong_answer_budget,
                omission_budget=self.omission_budget,
                assessment=assessment,
            )

        action = VerificationAction.REVISE if recoverable else VerificationAction.DEFER
        reason = (
            "Risk exceeds budget and the verifier supplied a recoverable correction."
            if recoverable
            else "Risk exceeds budget and requires human review."
        )
        return ActionDecision(
            action=action,
            violated_budgets=tuple(violated),
            reason=reason,
            wrong_answer_budget=self.wrong_answer_budget,
            omission_budget=self.omission_budget,
            assessment=assessment,
        )