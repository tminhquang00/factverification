import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

from kg_store import KGStore


ENTITY_ID_PATTERN = re.compile(r"\b(?:\d{6}|[A-Za-z]{2,10}\d{2,6})\b")


class QueryIntent(str, Enum):
    ALL_PREREQUISITES = "all_prerequisites"


class CompletenessVerdict(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class QuerySpec:
    intent: QueryIntent
    subject_id: str
    kg_version: str
    scope: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpectedAnswerSet:
    values: FrozenSet[str]
    relation: str
    evidence: Tuple[Tuple[str, str, str], ...]
    reference_scope: str = "kg_relative"


@dataclass(frozen=True)
class AnswerCompletenessResult:
    verdict: CompletenessVerdict
    expected: FrozenSet[str]
    mentioned: FrozenSet[str]
    missing: FrozenSet[str]
    unexpected: FrozenSet[str]
    set_precision: Optional[float]
    set_recall: Optional[float]
    exact_set_match: Optional[bool]
    relation: Optional[str]
    reference_scope: str
    evidence: Tuple[Tuple[str, str, str], ...]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict.value
        for key in ["expected", "mentioned", "missing", "unexpected"]:
            data[key] = sorted(data[key])
        data["evidence"] = [list(triple) for triple in self.evidence]
        return data


def parse_query_spec(query: str, kg_version: str) -> Optional[QuerySpec]:
    """Parses the narrow, initial set-valued intent supported by the research pipeline."""
    normalized_query = str(query or "").lower()
    entity_ids = ENTITY_ID_PATTERN.findall(str(query or ""))
    if not entity_ids or "prerequisite" not in normalized_query:
        return None
    return QuerySpec(
        intent=QueryIntent.ALL_PREREQUISITES,
        subject_id=entity_ids[0],
        kg_version=kg_version,
    )


class AnswerCompletenessVerifier:
    """Compares response members with deterministic KG-derived expected answer sets."""

    def __init__(self, store: KGStore):
        self.store = store

    def expected_answers(self, spec: QuerySpec) -> Optional[ExpectedAnswerSet]:
        if spec.intent != QueryIntent.ALL_PREREQUISITES:
            return None
        if not self.store.has_course(spec.subject_id):
            return None

        values = frozenset(str(value) for value in self.store.get_prerequisites(spec.subject_id))
        evidence = tuple(
            (spec.subject_id, "requiresPrerequisite", value)
            for value in sorted(values)
        )
        return ExpectedAnswerSet(
            values=values,
            relation="requiresPrerequisite",
            evidence=evidence,
        )

    def extract_answer_members(self, response: str, spec: QuerySpec) -> FrozenSet[str]:
        members = {entity_id.upper() for entity_id in ENTITY_ID_PATTERN.findall(str(response or ""))}
        members.discard(spec.subject_id.upper())
        return frozenset(members)

    def verify(
        self,
        spec: QuerySpec,
        response: str,
        mentioned_values=None,
    ) -> AnswerCompletenessResult:
        expected_answers = self.expected_answers(spec)
        if expected_answers is None:
            return AnswerCompletenessResult(
                verdict=CompletenessVerdict.INDETERMINATE,
                expected=frozenset(),
                mentioned=frozenset(),
                missing=frozenset(),
                unexpected=frozenset(),
                set_precision=None,
                set_recall=None,
                exact_set_match=None,
                relation=None,
                reference_scope="kg_relative",
                evidence=tuple(),
                reason=f"No expected answer set is available for {spec.subject_id} and {spec.intent.value}.",
            )

        expected = frozenset(value.upper() for value in expected_answers.values)
        if mentioned_values is None:
            mentioned = self.extract_answer_members(response, spec)
        else:
            mentioned = frozenset(str(value).upper() for value in mentioned_values)

        missing = expected - mentioned
        unexpected = mentioned - expected
        intersection_size = len(expected & mentioned)
        set_precision = intersection_size / len(mentioned) if mentioned else 1.0
        set_recall = intersection_size / len(expected) if expected else 1.0
        exact_set_match = mentioned == expected
        verdict = CompletenessVerdict.INCOMPLETE if missing else CompletenessVerdict.COMPLETE
        reason = (
            f"Response omitted {len(missing)} of {len(expected)} KG-derived required answers."
            if missing
            else f"Response includes all {len(expected)} KG-derived required answers."
        )

        return AnswerCompletenessResult(
            verdict=verdict,
            expected=expected,
            mentioned=mentioned,
            missing=missing,
            unexpected=unexpected,
            set_precision=set_precision,
            set_recall=set_recall,
            exact_set_match=exact_set_match,
            relation=expected_answers.relation,
            reference_scope=expected_answers.reference_scope,
            evidence=expected_answers.evidence,
            reason=reason,
        )