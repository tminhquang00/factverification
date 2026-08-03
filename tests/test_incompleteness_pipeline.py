import json
import tempfile
import unittest
from pathlib import Path

from kg_store import get_kg_store
from scripts.build_degraded_graphs import degrade_graph, degraded_declaration
from scripts.diagnose_routing_occupancy import validate_output_path
from scripts.generate_nusmods_questions import build_questions, counts_for_total
from scripts.run_incompleteness_pilot import mechanical_gold_for_graph
from verification_pipeline import VerificationPipeline


class FakeLLM:
    pass


class SequenceLLM:
    def __init__(self, responses):
        self.responses = iter(responses)

    def generate_json(self, *_args, **_kwargs):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


class CompletenessDeclarationTests(unittest.TestCase):
    def _pipeline(self, graph, declaration, routing="declared"):
        temp_dir = Path(tempfile.mkdtemp())
        graph_path = temp_dir / "graph.json"
        declaration_path = temp_dir / "completeness.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        declaration_path.write_text(json.dumps(declaration), encoding="utf-8")
        pipeline = VerificationPipeline.__new__(VerificationPipeline)
        pipeline.store = get_kg_store(str(graph_path), str(declaration_path))
        pipeline.routing_mode = routing
        pipeline.cwa_threshold = 0.85
        pipeline.enable_dense_linking = False
        pipeline.bi_encoder = None
        pipeline.entity_link_threshold = 0.95
        pipeline.entity_index = {}
        pipeline.entity_keys_list = []
        pipeline.entity_codes_list = []
        pipeline.entity_embeddings = None
        pipeline.build_entity_index()
        return pipeline

    def test_declared_completeness_overrides_low_occupancy(self):
        graph = {
            "A": {"course_id": "A", "prerequisites": []},
            "B": {"course_id": "B", "prerequisites": [{"course_id": "X"}]},
        }
        pipeline = self._pipeline(graph, {"relations": {"requiresPrerequisite": "complete"}})
        self.assertEqual(pipeline.get_world_assumption("requiresPrerequisite"), "closed")

    def test_declared_incomplete_overrides_high_occupancy(self):
        graph = {str(i): {"course_id": str(i), "credits": 4} for i in range(10)}
        pipeline = self._pipeline(graph, {"relations": {"hasCreditValue": "incomplete"}})
        self.assertEqual(pipeline.get_world_assumption("hasCreditValue"), "open")

    def test_explicit_empty_prerequisite_set_is_supported(self):
        graph = {"A": {"course_id": "A", "prerequisites": []}}
        pipeline = self._pipeline(graph, {"relations": {"requiresPrerequisite": "complete"}})
        result = pipeline.stage_4_verify_triple("A", "requiresPrerequisite", "none")
        self.assertEqual(result["verdict"], "Supported")

    def test_removed_prerequisite_field_is_unknown_when_declared_incomplete(self):
        graph = {"A": {"course_id": "A"}}
        pipeline = self._pipeline(graph, {"relations": {"requiresPrerequisite": "incomplete"}})
        result = pipeline.stage_4_verify_triple("A", "requiresPrerequisite", "none")
        self.assertEqual(result["verdict"], "Not-in-KG")

    def test_semester_membership_is_verified(self):
        graph = {"A": {"course_id": "A", "semesters": ["1", "2"]}}
        declaration = {"relations": {"offeredInTerm": "complete"}}
        pipeline = self._pipeline(graph, declaration)
        self.assertEqual(
            pipeline.stage_4_verify_triple("A", "offeredInTerm", "Semester 2")["verdict"],
            "Supported",
        )
        self.assertEqual(
            pipeline.stage_4_verify_triple("A", "offeredInTerm", "Semester 3")["verdict"],
            "Contradicted",
        )

    def test_semester_occupancy_uses_the_semesters_field(self):
        graph = {
            "A": {"course_id": "A", "semesters": ["1"]},
            "B": {"course_id": "B"},
        }
        pipeline = self._pipeline(graph, {"relations": {}}, routing="occupancy")
        self.assertEqual(pipeline.store.estimate_relation_occupancy("offeredInTerm"), 0.5)

    def test_preclusion_membership_and_missingness_are_world_aware(self):
        graph = {
            "A": {"course_id": "A", "preclusions": ["B"]},
            "B": {"course_id": "B", "preclusions": []},
            "C": {"course_id": "C"},
        }
        closed = self._pipeline(graph, {"relations": {"preclusions": "complete"}})
        opened = self._pipeline(graph, {"relations": {"preclusions": "incomplete"}})
        self.assertEqual(closed.stage_4_verify_triple("A", "preclusions", "B")["verdict"], "Supported")
        self.assertEqual(closed.stage_4_verify_triple("B", "preclusions", "none")["verdict"], "Supported")
        self.assertEqual(closed.stage_4_verify_triple("A", "preclusions", "C")["verdict"], "Contradicted")
        self.assertEqual(opened.stage_4_verify_triple("C", "preclusions", "B")["verdict"], "Not-in-KG")

    def test_nusmods_entity_score_is_not_forced_to_one(self):
        graph = {"CS1010": {"course_id": "CS1010", "credits": 4}}
        pipeline = self._pipeline(graph, {"relations": {"hasCreditValue": "complete"}})
        score = pipeline.calculate_confidence(
            "CS1010", "hasCreditValue", 8, "Contradicted",
            entity_score=0.4, decomp_agreement=0.5,
        )
        self.assertAlmostEqual(score, 0.2)

    def test_credit_verification_normalizes_numeric_string(self):
        graph = {"A": {"course_id": "A", "credits": 12}}
        pipeline = self._pipeline(graph, {"relations": {"hasCreditValue": "complete"}})
        self.assertEqual(
            pipeline.stage_4_verify_triple("A", "hasCreditValue", "12")["verdict"],
            "Supported",
        )

    def test_canonical_edge_object_need_not_be_an_entity_node(self):
        graph = {
            "CS2000": {
                "course_id": "CS2000",
                "prerequisites": [{"course_id": "OLD1000"}],
                "preclusions": ["EXT2000"],
            }
        }
        pipeline = self._pipeline(
            graph,
            {"relations": {"requiresPrerequisite": "complete", "preclusions": "complete"}},
        )
        prerequisite, _score = pipeline.stage_3_map_claim_to_triple(
            {
                "subject": "CS2000",
                "relation": "requiresPrerequisite",
                "object": "OLD1000",
                "claim_type": "requiresPrerequisite",
            },
            include_metadata=True,
        )
        preclusion, _score = pipeline.stage_3_map_claim_to_triple(
            {
                "subject": "CS2000",
                "relation": "preclusions",
                "object": "EXT2000",
                "claim_type": "preclusions",
            },
            include_metadata=True,
        )
        self.assertEqual(prerequisite, ("CS2000", "requiresPrerequisite", "OLD1000"))
        self.assertEqual(preclusion, ("CS2000", "preclusions", "EXT2000"))
        self.assertEqual(pipeline.stage_4_verify_triple(*prerequisite)["verdict"], "Supported")
        self.assertEqual(pipeline.stage_4_verify_triple(*preclusion)["verdict"], "Supported")

    def test_institutional_relation_phrases_are_canonicalized(self):
        graph = {
            "CS2000": {
                "course_id": "CS2000",
                "credits": 4,
                "semesters": ["2"],
                "prerequisites": [{"course_id": "CS1000"}],
                "preclusions": ["CS2001"],
            }
        }
        pipeline = self._pipeline(
            graph,
            {"relations": {
                "hasCreditValue": "complete",
                "offeredInTerm": "complete",
                "requiresPrerequisite": "complete",
                "preclusions": "complete",
            }},
        )
        cases = [
            ("is worth 4 modular credits", "4", "hasCreditValue"),
            ("is offered in Semester 2", "Semester 2", "offeredInTerm"),
            ("requires CS1000", "CS1000", "requiresPrerequisite"),
            ("precludes CS2001", "CS2001", "preclusions"),
        ]
        for relation, obj, expected_relation in cases:
            triple, _score = pipeline.stage_3_map_claim_to_triple(
                {
                    "subject": "CS2000",
                    "relation": relation,
                    "object": obj,
                    "claim_type": relation,
                },
                include_metadata=True,
            )
            self.assertEqual(triple[1], expected_relation)
            self.assertEqual(pipeline.stage_4_verify_triple(*triple)["verdict"], "Supported")

    def test_value_is_recovered_from_institutional_relation_phrase(self):
        graph = {
            "CS1231": {
                "course_id": "CS1231",
                "credits": 4,
                "semesters": ["2"],
                "prerequisites": [{"course_id": "CS1010"}],
                "preclusions": ["MA1101R"],
            }
        }
        pipeline = self._pipeline(
            graph,
            {"relations": {
                "hasCreditValue": "complete",
                "offeredInTerm": "complete",
                "requiresPrerequisite": "complete",
                "preclusions": "complete",
            }},
        )
        cases = [
            ("is offered in Term 2", "offeredInTerm", "2"),
            ("is worth 4 modular credits", "hasCreditValue", 4),
            ("requires CS1010", "requiresPrerequisite", "CS1010"),
            ("precludes MA1101R", "preclusions", "MA1101R"),
        ]
        for relation, claim_type, expected_object in cases:
            with self.subTest(relation=relation):
                triple = pipeline.stage_3_map_claim_to_triple({
                    "subject": "CS1231",
                    "relation": relation,
                    "object": None,
                    "claim_type": claim_type,
                })
                self.assertEqual(triple[1:], (claim_type, expected_object))

    def test_missing_institutional_value_is_object_unresolved(self):
        pipeline = self._pipeline(
            {"CS1231": {"course_id": "CS1231", "credits": 4, "semesters": ["1"]}},
            {"relations": {"hasCreditValue": "complete", "offeredInTerm": "complete"}},
        )
        for relation in ("hasCreditValue", "offeredInTerm"):
            with self.subTest(relation=relation):
                triple = pipeline.stage_3_map_claim_to_triple({
                    "subject": "CS1231",
                    "relation": relation,
                    "object": None,
                    "claim_type": relation,
                })
                self.assertEqual(triple[1], "object_unresolved")
                self.assertEqual(
                    pipeline.stage_4_verify_triple(*triple)["verdict"],
                    "Not-in-KG",
                )

    def test_null_object_is_not_an_explicit_empty_set_claim(self):
        graph = {
            "CS1231": {
                "course_id": "CS1231",
                "title": "Discrete Structures",
                "prerequisites": [],
                "preclusions": [],
                "semesters": ["1"],
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "graph.json"
            declaration_path = Path(temp_dir) / "completeness.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            declaration_path.write_text(json.dumps({
                "default": "incomplete",
                "relations": {
                    "requiresPrerequisite": "incomplete",
                    "preclusions": "incomplete",
                    "offeredInTerm": "incomplete",
                },
            }), encoding="utf-8")
            store = get_kg_store(str(graph_path), str(declaration_path))
            for relation in ("requiresPrerequisite", "preclusions", "offeredInTerm"):
                self.assertEqual(
                    mechanical_gold_for_graph(("CS1231", relation, None), graph, store),
                    "Not-in-KG",
                )

    def test_mechanical_gold_does_not_call_stage4(self):
        graph = {"A": {"course_id": "A", "credits": 4}}
        pipeline = self._pipeline(graph, {"relations": {"hasCreditValue": "complete"}})
        pipeline.stage_4_verify_triple = lambda *_args: (_ for _ in ()).throw(AssertionError())
        self.assertEqual(
            mechanical_gold_for_graph(("A", "hasCreditValue", 4), graph, pipeline.store),
            "Supported",
        )
        self.assertEqual(
            mechanical_gold_for_graph(("A", "hasCreditValue", 8), graph, pipeline.store),
            "Contradicted",
        )

    def test_mechanical_gold_normalizes_school_and_person_surface_forms(self):
        graph = {
            "A": {
                "course_id": "A",
                "school": "Science",
                "coordinator": "Dr Samuel Ippolito",
            }
        }
        pipeline = self._pipeline(
            graph,
            {"relations": {"partOfSchool": "complete", "taughtBy": "complete"}},
        )
        self.assertEqual(
            mechanical_gold_for_graph(
                ("A", "partOfSchool", "School of Science"), graph, pipeline.store
            ),
            "Supported",
        )
        self.assertEqual(
            mechanical_gold_for_graph(
                ("A", "taughtBy", "Dr. Samuel Ippolito"), graph, pipeline.store
            ),
            "Supported",
        )


class DegradationTests(unittest.TestCase):
    GRAPH = {
        "A": {"course_id": "A", "department": "D1", "credits": 4,
              "prerequisites": [{"course_id": "X"}, {"course_id": "Y"}]},
        "B": {"course_id": "B", "department": "D1", "credits": 4,
              "prerequisites": []},
        "C": {"course_id": "C", "department": "D2", "credits": 8,
              "prerequisites": [{"course_id": "Z"}]},
        "D": {"course_id": "D", "department": "D2", "credits": 4,
              "prerequisites": []},
    }

    def test_random_deletion_is_reproducible_and_does_not_mutate_source(self):
        first = degrade_graph(self.GRAPH, 0.5, "random", 7, ["hasCreditValue"])
        second = degrade_graph(self.GRAPH, 0.5, "random", 7, ["hasCreditValue"])
        self.assertEqual(first, second)
        self.assertIn("credits", self.GRAPH["A"])
        self.assertEqual(len(first[1]), 2)

    def test_deleted_nonempty_set_is_not_rewritten_as_known_empty(self):
        degraded, deleted, _stats = degrade_graph(
            self.GRAPH, 0.0, "random", 7, ["requiresPrerequisite"]
        )
        self.assertNotIn("prerequisites", degraded["A"])
        self.assertEqual(degraded["B"]["prerequisites"], [])
        self.assertEqual(len(deleted), 3)

    def test_degraded_relation_is_declared_incomplete(self):
        base = {"relations": {"hasCreditValue": "complete", "partOfSchool": "complete"}}
        result = degraded_declaration(base, 0.5, ["hasCreditValue"])
        self.assertEqual(result["relations"]["hasCreditValue"], "incomplete")
        self.assertEqual(result["relations"]["partOfSchool"], "complete")

    def test_diagnostic_output_cannot_overwrite_a_source_graph(self):
        with self.assertRaises(ValueError):
            validate_output_path("data/nusmods_graph.json")
        validate_output_path("output/diagnostics/routing_occupancy.json")


class QuestionGenerationTests(unittest.TestCase):
    def test_generation_is_deterministic_and_schema_diverse(self):
        graph = {}
        for index in range(40):
            code = f"AA{index:04d}"
            graph[code] = {
                "course_id": code,
                "title": code,
                "credits": 4,
                "school": "Science",
                "department": "Department",
                "semesters": ["1", "2"],
                "prerequisites": [],
            }
        for index in range(12):
            code = f"AA{index:04d}"
            intermediate = f"AA{index + 12:04d}"
            graph[code]["prerequisites"] = [{"course_id": intermediate}]
            graph[intermediate]["prerequisites"] = [{"course_id": f"AA{index + 24:04d}"}]
        graph["AA0039"]["prerequisites"] = [
            {"course_id": "AA0037"}, {"course_id": "AA0038"}
        ]
        counts = {
            "scalar-credit": 1,
            "set-membership-term": 1,
            "prerequisite-existence": 2,
            "conjunction": 1,
            "prerequisite-exhaustiveness": 2,
            "prerequisite-multi-hop": 1,
            "mixed-fact-advice": 1,
        }
        first = build_questions(graph, seed=9, counts=counts)
        second = build_questions(graph, seed=9, counts=counts)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 9)
        self.assertEqual(len({row["question_type"] for row in first}), 7)

    def test_scaled_counts_have_the_exact_requested_total(self):
        counts = counts_for_total(200)
        self.assertEqual(sum(counts.values()), 200)
        self.assertGreater(counts["preclusion-existence"], 0)
        self.assertGreater(counts["staffing-open-world"], 0)


class DecompositionConsistencyTests(unittest.TestCase):
    def _pipeline(self, responses):
        pipeline = VerificationPipeline.__new__(VerificationPipeline)
        pipeline.llm_client = SequenceLLM(responses)
        pipeline.store = type("Store", (), {"courses": {str(i): {} for i in range(50)}})()
        pipeline.last_decomp_agreement = 1.0
        return pipeline

    def test_intentional_empty_second_pass_does_not_fall_back(self):
        claim = {"subject": "CS1010", "relation": "hasCreditValue", "object": "4"}
        pipeline = self._pipeline([{"claims": [claim]}, {"claims": []}])
        claims, agreement = pipeline.stage_2_decompose("CS1010 is worth four credits", include_metadata=True)
        self.assertEqual(claims, [])
        self.assertEqual(agreement, 0.0)

    def test_failed_second_pass_falls_back_to_first(self):
        claim = {"subject": "CS1010", "relation": "hasCreditValue", "object": "4"}
        pipeline = self._pipeline([{"claims": [claim]}, RuntimeError("offline")])
        claims, agreement = pipeline.stage_2_decompose("CS1010 is worth four credits", include_metadata=True)
        self.assertEqual(claims, [claim])
        self.assertEqual(agreement, 1.0)


if __name__ == "__main__":
    unittest.main()
