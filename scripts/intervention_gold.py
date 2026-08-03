"""Gold labels derived from the deletion intervention, not from completeness metadata.

Why this module exists
----------------------
The earlier gold function (``run_incompleteness_pilot.mechanical_gold_for_graph``) decided whether
an absent fact should be called ``Contradicted`` or ``Not-in-KG`` by reading
``store.get_declared_world_assumption(relation)`` — the *same* completeness declaration file that
the proposed ``declared`` routing mode reads, and with the same branch structure. Gold and system
were therefore two implementations of one definition. The proposed system could not lose: it scored
exactly 1.000 accuracy and 1.000 macro-F1 in every single experimental condition, with a degenerate
[1.0, 1.0] bootstrap interval. That is the signature of a tautology, not of a measurement.

This module removes the circularity. Gold here is a function of two things only:

1. ``full_graph``  — the undegraded snapshot, which we treat as the reference world state;
2. ``condition_graph`` — the graph the system under test was actually allowed to see.

No declaration file is read at any point. A completeness declaration is now purely a *system input*
that can be right, wrong, stale, or missing, and the score can detect the difference.

The truth table
---------------
Two independent facts are established for each claimed triple ``(subject, relation, object)``:

``world_truth`` — what is true in the reference world (the full graph):

  * ``true``     the full graph asserts exactly this fact;
  * ``false``    the full graph asserts some value for this (subject, relation) and it is not this
                 one, so the claim conflicts with the reference world;
  * ``unknown``  the full graph itself says nothing about this (subject, relation). NUSMods
                 staffing (``taughtBy``) is the deliberate example: it is naturally incomplete and
                 is never artificially degraded, so it anchors genuine open-world absence.

``evidence_state`` — what survives in the condition graph the system could see:

  * ``confirming``  the condition graph still asserts the claimed fact;
  * ``conflicting`` the condition graph asserts a value for this (subject, relation) that differs
                    from the claim;
  * ``absent``      the condition graph asserts nothing for this (subject, relation), either
                    because our intervention deleted it or because it was never there.

The gold verdict is the strongest label the *available evidence* justifies:

  =============== ================ =====================================================
  world_truth     evidence_state   gold verdict
  =============== ================ =====================================================
  true            confirming       Supported
  true            absent           Not-in-KG   <- deleted a true fact; calling this
                                               Contradicted is the harm we measure
  false           conflicting      Contradicted
  false           absent           Not-in-KG   <- the conflicting value was deleted, so
                                               nothing licenses a contradiction any more
  unknown         absent           Not-in-KG   <- natural open-world absence
  =============== ================ =====================================================

The combinations ``true``/``conflicting`` and ``unknown``/``conflicting`` cannot occur, because the
degradation builder only ever *removes* facts and never adds or edits them. If they are ever
observed, either the condition graph did not come from our intervention or the evidence classifier
is wrong; the row is flagged with ``anomaly`` and, in ``strict`` mode, raises.

Set-valued relations are the subtle case
----------------------------------------
Random deletion removes *individual members* of a collection and leaves the container behind. A
course whose reference prerequisite list is ``[ES2002, ES2660, IS2101, LC1016]`` can end up with a
condition list of just ``[ES2660]``. A naive "is the field present?" test then treats the shrunken
list as an authoritative statement and reads the absence of ``ES2002`` as a *contradiction* — even
though ``ES2002`` really is a prerequisite and is missing only because we deleted it.

An earlier revision of this module had exactly that bug. It mislabelled 230 of 296 supposed
contradictions in a single experimental cell, and made a correctly-abstaining system look as though
it were missing 86% of the contradictions it should have caught. The published "over-abstention"
finding derived from it was withdrawn.

The rule is therefore: for a set relation, the absence of a claimed member licenses ``conflicting``
only when the visible member set is provably identical to the reference member set. Otherwise the
evidence state is ``absent``.

Honest reading of this definition
---------------------------------
Operationally this coincides with certain-answer semantics over the visible graph: absence never
licenses a contradiction. Two consequences must be stated plainly rather than buried.

* Any system that refuses to emit ``Contradicted`` from absence gets a false-contradiction rate of
  zero here *by construction*. ``declared_oracle`` is such a system whenever every degraded
  relation is correctly declared incomplete. Its zero is therefore an **upper bound / reference
  implementation**, not an empirical win, and the study reports it that way.
* The scientific content lives in the arms that *can* emit a contradiction from absence —
  ``binary``, ``declared_stale``, ``occupancy_*``, and the LLM verifier baselines. Those are
  measured against a gold they do not define.

Because ``world_truth`` is recorded on every row, the artifact also supports the sharper and
completely declaration-free safety metric used in the report: of the claims that are **true in the
reference world**, what fraction did the system call ``Contradicted``? That quantity needs no
convention about absence at all.
"""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.run_incompleteness_pilot import (  # noqa: E402
    graph_fact_present,
    normalize,
    normalize_person,
    normalize_school,
)

# Ontology relation -> the record field the parser stores it under. A relation is "asserted" for a
# subject when this field is present on the record with a non-placeholder value.
RELATION_FIELDS = {
    "hasCreditValue": ("credits",),
    "partOfSchool": ("school",),
    "requiresPrerequisite": ("prerequisites",),
    "preclusions": ("preclusions",),
    "offeredInTerm": ("semesters",),
    "taughtBy": ("coordinator", "coordinator_email"),
}

PLACEHOLDERS = (None, "", "Unknown")

# Object strings that assert emptiness rather than naming a value ("has no prerequisites").
SET_NEGATIONS = {
    "requiresPrerequisite": {"none", "no", "no prerequisites", "no prerequisite", "null"},
    "preclusions": {"none", "no", "no preclusions", "no preclusion", "null"},
    "offeredInTerm": {"none", "no", "no semesters", "null"},
}

NON_DECISION_RELATIONS = {"entity_unresolved", "object_unresolved"}

# Relations whose value is a *collection*. These need special handling: random deletion removes
# individual members and leaves the container in place, so a present-but-shrunken list is NOT an
# authoritative statement about what the subject has. See `classify_evidence_state`.
SET_RELATION_FIELDS = {
    "requiresPrerequisite": "prerequisites",
    "preclusions": "preclusions",
    "offeredInTerm": "semesters",
}


class InterventionError(ValueError):
    """Raised when a condition graph is not a pure deletion of the reference graph."""


def _is_set_relation(relation):
    return relation in SET_RELATION_FIELDS


def _member_key(item):
    """Canonical identity of one member of a set-valued relation."""
    if isinstance(item, dict):
        return normalize(item.get("course_id") or item.get("id") or item)
    return normalize(item)


def member_set(graph, subject, relation):
    """Members recorded for ``(subject, relation)``, or ``None`` when the field is absent.

    ``None`` and ``set()`` mean different things and must stay distinguishable: ``None`` is "the
    graph does not say", while ``set()`` is the parser's explicit "this course has no
    prerequisites".
    """
    record = graph.get(str(subject))
    if not record:
        return None
    field = SET_RELATION_FIELDS.get(relation)
    if field is None or field not in record:
        return None
    return {_member_key(item) for item in (record.get(field) or [])}


def relation_asserted(graph, subject, relation):
    """True when the graph records any value for ``(subject, relation)``.

    For set-valued relations an explicit empty list still counts as an assertion: the NUSMods
    parser deliberately writes ``"prerequisites": []`` so that "this course has no prerequisites"
    stays distinguishable from "prerequisite information is unavailable". Degradation removes the
    key entirely rather than emptying it, which is what makes the two cases separable here.
    """
    record = graph.get(str(subject))
    if not record:
        return False
    fields = RELATION_FIELDS.get(relation)
    if fields is None:
        # Open-domain / unmapped relation: fall back to the relation name as the field key.
        fields = (relation,)
    for field in fields:
        if field not in record:
            continue
        value = record.get(field)
        if isinstance(value, list):
            return True  # an explicit list, empty or not, is an assertion
        if value not in PLACEHOLDERS:
            return True
    return False


def classify_world_truth(triple, full_graph):
    """Returns ``true``, ``false`` or ``unknown`` for the claim against the reference world."""
    subject, relation, obj = triple
    if graph_fact_present(full_graph, triple):
        return "true"
    if relation_asserted(full_graph, subject, relation):
        # The reference world commits to a value for this slot and it is not the claimed one.
        # For a set relation, an explicit empty list plus a negation object is handled by
        # graph_fact_present above, so reaching here means a genuine mismatch.
        return "false"
    return "unknown"


def classify_evidence_state(triple, condition_graph, reference_graph=None):
    """Returns ``confirming``, ``conflicting`` or ``absent`` for the graph under test.

    Set-valued relations need the reference graph as well, and the reason is subtle enough to be
    worth stating in full.

    Random deletion removes *individual members* of a set and leaves the container behind. A course
    whose reference prerequisite list is ``[ES2002, ES2660, IS2101, LC1016]`` can end up with a
    condition list of just ``[ES2660]``. The key ``prerequisites`` is still present, so a naive
    "is the field there?" test concludes that the graph makes an authoritative statement, and then
    reads the absence of ``ES2002`` as a *conflict*. That is wrong: ``ES2002`` really is a
    prerequisite, and the only reason it is not visible is that we deleted it.

    Getting this wrong is not a rounding error. In an earlier revision it mislabelled 230 of 296
    supposed contradictions in a single experimental cell, and made a correctly-abstaining system
    look as though it were missing 86% of the contradictions it should have caught.

    So for a set relation the absence of a claimed member licenses ``conflicting`` only when the
    visible member set is provably identical to the reference member set — that is, when nothing was
    removed for this particular subject and relation. Otherwise the evidence is simply ``absent``.
    """
    subject, relation, obj = triple
    if graph_fact_present(condition_graph, triple):
        return "confirming"

    if _is_set_relation(relation):
        condition_members = member_set(condition_graph, subject, relation)
        if condition_members is None:
            return "absent"
        if reference_graph is None:
            # Without the reference we cannot tell a complete set from a depleted one. Abstain
            # rather than risk manufacturing a contradiction out of our own intervention.
            return "absent"
        reference_members = member_set(reference_graph, subject, relation)
        if reference_members is None:
            return "absent"
        if condition_members == reference_members:
            # Nothing was removed here, so the visible set is authoritative and the claimed member
            # genuinely is not in it.
            return "conflicting"
        return "absent"

    if relation_asserted(condition_graph, subject, relation):
        return "conflicting"
    return "absent"


def intervention_gold(triple, full_graph, condition_graph, strict=False):
    """Gold verdict for ``triple`` from graph contents alone; no declaration is consulted.

    Returns a dict with ``verdict``, ``world_truth``, ``evidence_state`` and ``basis`` so that the
    saved row-level artifact can be re-analysed under a different convention about absence without
    re-running anything.

    ``strict=True`` raises :class:`InterventionError` on a world/evidence combination that pure
    deletion cannot produce. The sweep leaves it False and counts anomalies instead, so that one
    malformed record cannot abort a multi-hour rescore.
    """
    subject, relation, obj = triple

    if relation == "unclassified":
        return {
            "verdict": "Out-of-scope",
            "world_truth": "not_applicable",
            "evidence_state": "not_applicable",
            "basis": "no schema-supported factual claim to evaluate",
            "anomaly": None,
        }
    if relation in NON_DECISION_RELATIONS or not subject:
        return {
            "verdict": "Not-in-KG",
            "world_truth": "not_applicable",
            "evidence_state": "not_applicable",
            "basis": "claim could not be grounded to a subject or object the graph names",
            "anomaly": None,
        }
    if full_graph.get(str(subject)) is None:
        return {
            "verdict": "Not-in-KG",
            "world_truth": "unknown",
            "evidence_state": "absent",
            "basis": "the reference world contains no record for this subject",
            "anomaly": None,
        }

    world_truth = classify_world_truth(triple, full_graph)
    evidence_state = classify_evidence_state(triple, condition_graph, full_graph)
    anomaly = None

    if evidence_state == "conflicting" and world_truth == "true":
        # Pure deletion cannot make a true fact conflict with the visible graph. If this fires, the
        # evidence classifier has misread a depleted collection as an authoritative one — exactly
        # the bug `classify_evidence_state` documents.
        anomaly = "true_fact_reported_as_conflicting"
        message = (
            f"{triple!r} is true in the reference graph yet the condition graph was read as "
            "conflicting. Pure deletion cannot produce this; the evidence classifier is wrong."
        )
        if strict:
            raise InterventionError(message)
        evidence_state = "absent"

    if evidence_state == "confirming" and world_truth == "false":
        # Deletion emptied a set, so an explicit-empty-set claim ("has no prerequisites") is now
        # confirmed by the visible graph even though it is false in the reference world. The
        # verdict below stays `Supported`, because that genuinely is what the available evidence
        # says, but the row is flagged so this artifact can be counted rather than hidden.
        anomaly = "deletion_induced_false_support"
        if strict:
            raise InterventionError(
                f"{triple!r} is confirmed by the condition graph but false in the reference graph."
            )

    if evidence_state == "confirming":
        verdict = "Supported"
        basis = "the visible graph asserts exactly this fact"
    elif evidence_state == "conflicting":
        verdict = "Contradicted"
        basis = "the visible graph asserts a different value for this subject and relation"
    else:
        verdict = "Not-in-KG"
        if world_truth == "true":
            basis = "the fact is true in the reference world but our intervention removed it"
        elif world_truth == "false":
            basis = "the conflicting reference value is no longer visible, so nothing licenses a contradiction"
        else:
            basis = "the reference world itself is silent here (natural open-world absence)"

    return {
        "verdict": verdict,
        "world_truth": world_truth,
        "evidence_state": evidence_state,
        "basis": basis,
        "anomaly": anomaly,
    }


def is_anomalous(gold_record):
    """True when the row hit a world/evidence combination pure deletion should not produce."""
    return gold_record.get("anomaly") is not None


__all__ = [
    "InterventionError",
    "classify_evidence_state",
    "classify_world_truth",
    "intervention_gold",
    "relation_asserted",
]
