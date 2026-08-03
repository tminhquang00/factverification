"""Tests for declaration-independent gold and the routing arms measured against it.

The point of these tests is not only that the truth table is implemented correctly. It is that gold
stays *independent of the systems under test*: the regression that motivated this module was a gold
function which read the same completeness declaration as the proposed routing mode, so the proposed
mode scored exactly 1.000 everywhere by construction. `GoldIndependenceTests` below is the guard
against that mistake reappearing.
"""

import json
import tempfile
import unittest
from pathlib import Path

from kg_store import get_kg_store
from scripts.intervention_gold import (
    InterventionError,
    classify_evidence_state,
    classify_world_truth,
    intervention_gold,
    relation_asserted,
)
from verification_pipeline import VerificationPipeline


# A two-module reference world. CS1010 carries every degradable relation; CS2020 exists so that
# "subject present but relation absent" and "subject absent entirely" stay distinguishable.
REFERENCE_WORLD = {
    "CS1010": {
        "course_id": "CS1010",
        "credits": "4",
        "school": "School of Computing",
        "prerequisites": [],
        "preclusions": ["CS1101"],
        "semesters": ["1", "2"],
    },
    "CS2020": {
        "course_id": "CS2020",
        "credits": "8",
        "prerequisites": [{"course_id": "CS1010"}],
    },
}


def condition_graph_without(subject, *fields):
    """Copy of the reference world with specific relation fields deleted, as the builder does."""
    graph = json.loads(json.dumps(REFERENCE_WORLD))
    for field in fields:
        graph[subject].pop(field, None)
    return graph


def build_pipeline(graph, declaration, routing="declared", cwa_threshold=0.85):
    temp_dir = Path(tempfile.mkdtemp())
    graph_path = temp_dir / "graph.json"
    declaration_path = temp_dir / "completeness.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    declaration_path.write_text(json.dumps(declaration), encoding="utf-8")
    pipeline = VerificationPipeline.__new__(VerificationPipeline)
    pipeline.store = get_kg_store(str(graph_path), str(declaration_path))
    pipeline.routing_mode = routing
    pipeline.cwa_threshold = cwa_threshold
    pipeline._missing_declaration_warned = set()
    return pipeline


COMPLETE_DECLARATION = {
    "default": "incomplete",
    "relations": {
        "hasCreditValue": "complete",
        "partOfSchool": "complete",
        "requiresPrerequisite": "complete",
        "preclusions": "complete",
        "offeredInTerm": "complete",
        "taughtBy": "incomplete",
    },
}

INCOMPLETE_DECLARATION = {
    "default": "incomplete",
    "relations": {relation: "incomplete" for relation in COMPLETE_DECLARATION["relations"]},
}


class TruthTableTests(unittest.TestCase):
    def assert_gold(self, triple, condition, verdict, world, evidence):
        result = intervention_gold(triple, REFERENCE_WORLD, condition)
        self.assertEqual(result["verdict"], verdict, result)
        self.assertEqual(result["world_truth"], world, result)
        self.assertEqual(result["evidence_state"], evidence, result)

    def test_true_fact_still_visible_is_supported(self):
        self.assert_gold(
            ("CS1010", "hasCreditValue", "4"), REFERENCE_WORLD,
            "Supported", "true", "confirming",
        )

    def test_true_fact_deleted_by_intervention_is_not_in_kg(self):
        """The central case. The claim is true; we removed the evidence; contradiction is wrong."""
        self.assert_gold(
            ("CS1010", "hasCreditValue", "4"), condition_graph_without("CS1010", "credits"),
            "Not-in-KG", "true", "absent",
        )

    def test_false_claim_with_conflicting_value_visible_is_contradicted(self):
        self.assert_gold(
            ("CS1010", "hasCreditValue", "5"), REFERENCE_WORLD,
            "Contradicted", "false", "conflicting",
        )

    def test_false_claim_loses_its_contradiction_once_evidence_is_deleted(self):
        """Nothing licenses a contradiction after the conflicting value is gone."""
        self.assert_gold(
            ("CS1010", "hasCreditValue", "5"), condition_graph_without("CS1010", "credits"),
            "Not-in-KG", "false", "absent",
        )

    def test_naturally_absent_relation_is_unknown_not_false(self):
        """taughtBy is never degraded; the reference world is simply silent about it."""
        self.assert_gold(
            ("CS1010", "taughtBy", "Dr Ada Lovelace"), REFERENCE_WORLD,
            "Not-in-KG", "unknown", "absent",
        )

    def test_explicit_empty_set_is_a_true_claim_not_an_absence(self):
        self.assert_gold(
            ("CS1010", "requiresPrerequisite", "none"), REFERENCE_WORLD,
            "Supported", "true", "confirming",
        )

    def test_deleting_the_set_field_makes_the_empty_set_claim_unknown(self):
        self.assert_gold(
            ("CS1010", "requiresPrerequisite", "none"),
            condition_graph_without("CS1010", "prerequisites"),
            "Not-in-KG", "true", "absent",
        )

    def test_subject_missing_from_reference_world_is_not_in_kg(self):
        result = intervention_gold(("ZZ9999", "hasCreditValue", "4"), REFERENCE_WORLD, REFERENCE_WORLD)
        self.assertEqual(result["verdict"], "Not-in-KG")
        self.assertEqual(result["world_truth"], "unknown")

    def test_unclassified_relation_is_out_of_scope(self):
        result = intervention_gold(("CS1010", "unclassified", "x"), REFERENCE_WORLD, REFERENCE_WORLD)
        self.assertEqual(result["verdict"], "Out-of-scope")

    def test_unresolved_entity_is_a_non_decision(self):
        for relation in ("entity_unresolved", "object_unresolved"):
            result = intervention_gold(("CS1010", relation, "x"), REFERENCE_WORLD, REFERENCE_WORLD)
            self.assertEqual(result["verdict"], "Not-in-KG")
            self.assertEqual(result["world_truth"], "not_applicable")

    def test_semester_membership_survives_normalisation(self):
        self.assert_gold(
            ("CS1010", "offeredInTerm", "Semester 2"), REFERENCE_WORLD,
            "Supported", "true", "confirming",
        )


class SetRelationDepletionTests(unittest.TestCase):
    """Regression tests for the set-member deletion bug.

    Random deletion removes individual members and leaves the container in place. Reading a
    shrunken list as an authoritative statement turned true-but-deleted facts into gold
    contradictions, which in turn made a correctly-abstaining system look badly broken.
    """

    WORLD = {
        "NHS2056": {
            "course_id": "NHS2056",
            "prerequisites": [
                {"course_id": "ES2002"}, {"course_id": "ES2660"},
                {"course_id": "IS2101"}, {"course_id": "LC1016"},
            ],
            "preclusions": ["CS1101", "CS1102"],
            "semesters": ["1", "2"],
        },
    }

    def depleted(self):
        """The list survives but three of its four members were deleted."""
        graph = json.loads(json.dumps(self.WORLD))
        graph["NHS2056"]["prerequisites"] = [{"course_id": "ES2660"}]
        return graph

    def test_deleted_set_member_is_absent_not_conflicting(self):
        triple = ("NHS2056", "requiresPrerequisite", "ES2002")
        result = intervention_gold(triple, self.WORLD, self.depleted())
        self.assertEqual(result["world_truth"], "true")
        self.assertEqual(result["evidence_state"], "absent")
        self.assertEqual(result["verdict"], "Not-in-KG")
        self.assertIsNone(result["anomaly"])

    def test_surviving_set_member_is_still_supported(self):
        triple = ("NHS2056", "requiresPrerequisite", "ES2660")
        result = intervention_gold(triple, self.WORLD, self.depleted())
        self.assertEqual(result["verdict"], "Supported")

    def test_intact_set_still_licenses_a_contradiction(self):
        """When nothing was removed, the visible set IS authoritative."""
        triple = ("NHS2056", "requiresPrerequisite", "CS9999")
        result = intervention_gold(triple, self.WORLD, self.WORLD)
        self.assertEqual(result["world_truth"], "false")
        self.assertEqual(result["evidence_state"], "conflicting")
        self.assertEqual(result["verdict"], "Contradicted")

    def test_false_claim_against_a_depleted_set_abstains(self):
        """A claim false in the world still cannot be contradicted from a depleted set."""
        triple = ("NHS2056", "requiresPrerequisite", "CS9999")
        result = intervention_gold(triple, self.WORLD, self.depleted())
        self.assertEqual(result["evidence_state"], "absent")
        self.assertEqual(result["verdict"], "Not-in-KG")

    def test_preclusion_sets_behave_the_same_way(self):
        graph = json.loads(json.dumps(self.WORLD))
        graph["NHS2056"]["preclusions"] = ["CS1101"]
        result = intervention_gold(("NHS2056", "preclusions", "CS1102"), self.WORLD, graph)
        self.assertEqual(result["world_truth"], "true")
        self.assertEqual(result["verdict"], "Not-in-KG")

    def test_semester_sets_behave_the_same_way(self):
        graph = json.loads(json.dumps(self.WORLD))
        graph["NHS2056"]["semesters"] = ["1"]
        result = intervention_gold(("NHS2056", "offeredInTerm", "Semester 2"), self.WORLD, graph)
        self.assertEqual(result["world_truth"], "true")
        self.assertEqual(result["verdict"], "Not-in-KG")

    def test_no_true_fact_is_ever_labelled_contradicted(self):
        """The invariant the bug violated: gold must never contradict a reference-world truth."""
        graph = self.depleted()
        for member in ("ES2002", "ES2660", "IS2101", "LC1016"):
            result = intervention_gold(("NHS2056", "requiresPrerequisite", member), self.WORLD, graph)
            self.assertNotEqual(result["verdict"], "Contradicted", member)

    def test_classifier_is_conservative_without_a_reference_graph(self):
        """With no reference to compare against, a depleted set must not read as conflicting."""
        state = classify_evidence_state(
            ("NHS2056", "requiresPrerequisite", "ES2002"), self.depleted(), reference_graph=None
        )
        self.assertEqual(state, "absent")

    def test_relation_asserted_alone_is_not_sufficient_for_set_relations(self):
        """The exact predicate that caused the bug: the key is present but proves nothing."""
        self.assertTrue(relation_asserted(self.depleted(), "NHS2056", "requiresPrerequisite"))
        self.assertEqual(
            classify_evidence_state(
                ("NHS2056", "requiresPrerequisite", "ES2002"), self.depleted(), self.WORLD
            ),
            "absent",
        )


class HelperTests(unittest.TestCase):
    def test_relation_asserted_treats_empty_list_as_an_assertion(self):
        self.assertTrue(relation_asserted(REFERENCE_WORLD, "CS1010", "requiresPrerequisite"))

    def test_relation_asserted_is_false_once_the_field_is_deleted(self):
        graph = condition_graph_without("CS1010", "prerequisites")
        self.assertFalse(relation_asserted(graph, "CS1010", "requiresPrerequisite"))

    def test_relation_asserted_ignores_placeholder_values(self):
        graph = {"CS1010": {"course_id": "CS1010", "school": "Unknown"}}
        self.assertFalse(relation_asserted(graph, "CS1010", "partOfSchool"))

    def test_world_and_evidence_classifiers_are_independent(self):
        triple = ("CS1010", "partOfSchool", "School of Computing")
        degraded = condition_graph_without("CS1010", "school")
        self.assertEqual(classify_world_truth(triple, REFERENCE_WORLD), "true")
        self.assertEqual(classify_evidence_state(triple, degraded), "absent")

    def test_strict_mode_rejects_a_graph_that_is_not_a_pure_deletion(self):
        fabricated = json.loads(json.dumps(REFERENCE_WORLD))
        fabricated["CS1010"]["credits"] = "12"
        with self.assertRaises(InterventionError):
            intervention_gold(("CS1010", "hasCreditValue", "12"), REFERENCE_WORLD, fabricated,
                              strict=True)

    def test_non_strict_mode_records_the_anomaly_instead_of_raising(self):
        fabricated = json.loads(json.dumps(REFERENCE_WORLD))
        fabricated["CS1010"]["credits"] = "12"
        result = intervention_gold(("CS1010", "hasCreditValue", "12"), REFERENCE_WORLD, fabricated)
        self.assertEqual(result["verdict"], "Supported")


class BinaryRoutingModeTests(unittest.TestCase):
    """`binary` must be a real pass over the graph, not a relabelling of another system."""

    def test_binary_has_no_not_in_kg_label_for_absent_facts(self):
        degraded = condition_graph_without("CS1010", "credits")
        pipeline = build_pipeline(degraded, INCOMPLETE_DECLARATION, routing="binary")
        result = pipeline.stage_4_verify_triple("CS1010", "hasCreditValue", "4")
        self.assertEqual(result["verdict"], "Contradicted")

    def test_binary_ignores_an_incomplete_declaration_entirely(self):
        """Even told the relation is incomplete, a binary checker cannot express that."""
        degraded = condition_graph_without("CS1010", "prerequisites")
        pipeline = build_pipeline(degraded, INCOMPLETE_DECLARATION, routing="binary")
        self.assertEqual(pipeline.get_world_assumption("requiresPrerequisite"), "closed")
        result = pipeline.stage_4_verify_triple("CS1010", "requiresPrerequisite", "CS0001")
        self.assertEqual(result["verdict"], "Contradicted")

    def test_binary_collapses_unresolvable_entities_too(self):
        pipeline = build_pipeline(REFERENCE_WORLD, INCOMPLETE_DECLARATION, routing="binary")
        result = pipeline.stage_4_verify_triple("CS1010", "entity_unresolved", "something")
        self.assertEqual(result["verdict"], "Contradicted")

    def test_binary_still_supports_a_visible_true_fact(self):
        pipeline = build_pipeline(REFERENCE_WORLD, INCOMPLETE_DECLARATION, routing="binary")
        result = pipeline.stage_4_verify_triple("CS1010", "hasCreditValue", "4")
        self.assertEqual(result["verdict"], "Supported")

    def test_binary_is_a_rejected_value_for_unknown_modes(self):
        with self.assertRaises(ValueError):
            VerificationPipeline(routing_mode="not_a_mode")


class StaleDeclarationTests(unittest.TestCase):
    """The realistic arm: metadata still claims completeness after the data has gone."""

    def test_stale_declaration_produces_a_false_contradiction(self):
        degraded = condition_graph_without("CS1010", "credits")
        stale = build_pipeline(degraded, COMPLETE_DECLARATION, routing="declared")
        prediction = stale.stage_4_verify_triple("CS1010", "hasCreditValue", "4")["verdict"]
        gold = intervention_gold(("CS1010", "hasCreditValue", "4"), REFERENCE_WORLD, degraded)
        self.assertEqual(prediction, "Contradicted")
        self.assertEqual(gold["verdict"], "Not-in-KG")
        self.assertEqual(gold["world_truth"], "true")

    def test_synchronised_declaration_avoids_that_false_contradiction(self):
        degraded = condition_graph_without("CS1010", "credits")
        synced = build_pipeline(degraded, INCOMPLETE_DECLARATION, routing="declared")
        prediction = synced.stage_4_verify_triple("CS1010", "hasCreditValue", "4")["verdict"]
        self.assertEqual(prediction, "Not-in-KG")

    def test_stale_declaration_is_harmless_while_the_data_is_intact(self):
        intact = build_pipeline(REFERENCE_WORLD, COMPLETE_DECLARATION, routing="declared")
        prediction = intact.stage_4_verify_triple("CS1010", "hasCreditValue", "4")["verdict"]
        gold = intervention_gold(("CS1010", "hasCreditValue", "4"), REFERENCE_WORLD, REFERENCE_WORLD)
        self.assertEqual(prediction, gold["verdict"])


class GoldIndependenceTests(unittest.TestCase):
    """Regression guard: gold must not be a function of any completeness declaration."""

    def test_gold_is_identical_under_opposite_declarations(self):
        degraded = condition_graph_without("CS1010", "credits", "school", "prerequisites")
        triples = [
            ("CS1010", "hasCreditValue", "4"),
            ("CS1010", "hasCreditValue", "5"),
            ("CS1010", "partOfSchool", "School of Computing"),
            ("CS1010", "requiresPrerequisite", "none"),
            ("CS1010", "taughtBy", "Dr Ada Lovelace"),
        ]
        # Gold takes graphs only; there is no declaration argument to vary. Assert that the two
        # routing systems built on opposite declarations disagree with each other while gold stays
        # fixed — that is exactly the discriminating power the old gold lacked.
        complete_side = build_pipeline(degraded, COMPLETE_DECLARATION, routing="declared")
        incomplete_side = build_pipeline(degraded, INCOMPLETE_DECLARATION, routing="declared")
        disagreements = 0
        for triple in triples:
            gold = intervention_gold(triple, REFERENCE_WORLD, degraded)["verdict"]
            self.assertIn(gold, {"Supported", "Contradicted", "Not-in-KG"})
            if (complete_side.stage_4_verify_triple(*triple)["verdict"]
                    != incomplete_side.stage_4_verify_triple(*triple)["verdict"]):
                disagreements += 1
        self.assertGreater(
            disagreements, 0,
            "the two declaration variants must be separable, otherwise the arm is not informative",
        )

    def test_a_system_can_actually_lose_points_against_this_gold(self):
        """The old gold made the proposed route unbeatable; this one must be losable."""
        degraded = condition_graph_without("CS1010", "credits", "school")
        stale = build_pipeline(degraded, COMPLETE_DECLARATION, routing="declared")
        binary = build_pipeline(degraded, COMPLETE_DECLARATION, routing="binary")
        triples = [
            ("CS1010", "hasCreditValue", "4"),
            ("CS1010", "partOfSchool", "School of Computing"),
        ]
        for pipeline in (stale, binary):
            errors = sum(
                pipeline.stage_4_verify_triple(*triple)["verdict"]
                != intervention_gold(triple, REFERENCE_WORLD, degraded)["verdict"]
                for triple in triples
            )
            self.assertEqual(errors, len(triples))


if __name__ == "__main__":
    unittest.main()
