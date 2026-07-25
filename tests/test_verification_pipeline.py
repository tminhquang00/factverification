from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

from verification_pipeline import VerificationPipeline


class FakeLLMClient:
    def generate_json(self, prompt, system_prompt=None, temperature=0.0):
        return {
            "claims": [
                {
                    "subject": "Low-confidence course",
                    "relation": "hasCreditValue",
                    "object": "12",
                    "claim_type": "hasCreditValue",
                }
            ]
        }


class FakeStore:
    courses = {
        "123456": {
            "credits": 12,
            "prerequisites": [{"course_id": "111111"}, {"course_id": "222222"}],
        }
    }

    def __init__(self, relation_score=1.0):
        self.relation_score = relation_score

    def has_course(self, course_id):
        return course_id in self.courses

    def get_course(self, course_id):
        return self.courses.get(course_id)

    def get_credits(self, course_id):
        return self.courses[course_id]["credits"]

    def get_prerequisites(self, course_id):
        return [item["course_id"] for item in self.courses[course_id]["prerequisites"]]

    def estimate_relation_completeness(self, relation):
        return self.relation_score

    def estimate_relation_occupancy(self, relation):
        return self.relation_score

    def get_relation_completeness(self, relation):
        return "closed"


class LocalScorePipeline(VerificationPipeline):
    def __init__(self):
        self.store = FakeStore()
        self.llm_client = FakeLLMClient()
        self.oracle_linking = False
        self.smooth_calibration = False
        self.routing_mode = "dynamic"
        self.cwa_threshold = 0.85
        self.abstention_threshold = 0.5
        self.last_entity_score = 0.99
        self.last_decomp_agreement = 0.99

    def link_entity(self, text, include_score=False):
        if include_score:
            return "123456", 0.4
        self.last_entity_score = 0.4
        return "123456"


class ContextStore:
    def __init__(self):
        self.courses = {"background": {"title": "Background"}}


class ContextPipeline(VerificationPipeline):
    def __init__(self):
        self.store = ContextStore()
        self.entity_index = {"background": "background"}
        self.entity_keys_list = ["background"]
        self.entity_codes_list = ["background"]
        self.entity_embeddings = "background-embeddings"
        self._context_lock = threading.RLock()

    def build_entity_index(self):
        subjects = sorted(self.store.courses)
        self.entity_index = {subject: subject for subject in subjects}
        self.entity_keys_list = subjects
        self.entity_codes_list = subjects
        self.entity_embeddings = tuple(subjects)

    def verify_statement(self, text, custom_system_prompt=None):
        return {"subjects": sorted(self.store.courses)}


class UnclassifiedRelationStore:
    """Background record carrying an open-domain relation key, as verify_with_context builds."""

    def __init__(self):
        self.courses = {
            "123456": {
                "course_id": "123456",
                "title": "123456",
                "credits": 12,
                "school": "Science",
                "coordinator": "Unknown",
                "coordinator_email": "Unknown",
                "prerequisites": [],
                "description": "",
                "college": "Auburn",
            }
        }


class UnclassifiedFallbackPipeline(VerificationPipeline):
    """Minimal pipeline exercising the unclassified-relation fallback in stage 3."""

    def __init__(self):
        self.store = UnclassifiedRelationStore()
        self.oracle_linking = False

    def link_entity(self, text, include_score=False):
        return ("123456", 1.0) if include_score else "123456"


class StageThreeFallbackTests(unittest.TestCase):
    """Regression coverage for the `mapped` name-shadowing defect.

    stage_3_map_claim_to_triple defines a local helper named `mapped`. A boolean flag
    inside the unclassified-relation fallback previously reused that name, so every
    later `return mapped(...)` raised TypeError: 'bool' object is not callable. That
    path is reached routinely on FactKG, where the harness converted each crash into a
    default label and silently scored it.
    """

    def test_unclassified_relation_fallback_returns_a_triple(self):
        pipeline = UnclassifiedFallbackPipeline()

        # Force the heuristic branch (no bi-encoder attribute) so the flag is exercised.
        triple, entity_score = pipeline.stage_3_map_claim_to_triple(
            {
                "subject": "123456",
                "relation": "unclassified",
                "object": "college",
                "claim_type": "unclassified",
            },
            include_metadata=True,
        )

        self.assertIsInstance(triple, tuple)
        self.assertEqual(len(triple), 3)
        self.assertEqual(entity_score, 1.0)
        # The fallback should resolve the open-domain relation present on the record.
        self.assertEqual(triple[1], "college")

    def test_mapped_helper_is_never_rebound(self):
        """The helper must still be callable after the fallback branch runs."""
        pipeline = UnclassifiedFallbackPipeline()

        for object_value in ("college", "something unrelated entirely", ""):
            with self.subTest(object_value=object_value):
                result = pipeline.stage_3_map_claim_to_triple(
                    {
                        "subject": "123456",
                        "relation": "unclassified",
                        "object": object_value,
                        "claim_type": "unclassified",
                    },
                    include_metadata=True,
                )
                self.assertIsInstance(result[0], tuple)


class VerificationMetadataTests(unittest.TestCase):
    def test_verify_statement_uses_claim_local_scores(self):
        pipeline = LocalScorePipeline()

        result = pipeline.verify_statement("The course is worth 12 credit points.")

        claim = result["claims"][0]
        self.assertEqual(result["overall_verdict"], "Supported")
        self.assertEqual(claim["confidence"], 0.4)
        self.assertEqual(claim["entity_linking_score"], 0.4)
        self.assertEqual(claim["decomposition_agreement"], 1.0)
        self.assertEqual(pipeline.last_entity_score, 0.99)
        self.assertEqual(pipeline.last_decomp_agreement, 0.99)

    def test_transient_contexts_are_isolated_and_restored(self):
        pipeline = ContextPipeline()
        background_courses = pipeline.store.courses
        background_index = pipeline.entity_index
        subjects = [f"subject-{index}" for index in range(20)]

        def verify(subject):
            result = pipeline.verify_with_context("claim", [[subject, "relation", "object"]])
            return result["subjects"]

        with ThreadPoolExecutor(max_workers=5) as executor:
            observed = list(executor.map(verify, subjects))

        self.assertEqual(observed, [[subject] for subject in subjects])
        self.assertIs(pipeline.store.courses, background_courses)
        self.assertIs(pipeline.entity_index, background_index)

    def test_world_assumption_treatments_are_distinct(self):
        pipeline = LocalScorePipeline()
        pipeline.store = FakeStore(relation_score=0.4)
        pipeline.cwa_threshold = 0.6

        pipeline.routing_mode = "dynamic"
        self.assertEqual(pipeline.get_world_assumption("taughtBy"), "open")

        pipeline.routing_mode = "fixed_cwa"
        self.assertEqual(pipeline.get_world_assumption("taughtBy"), "closed")

        pipeline.routing_mode = "fixed_owa"
        self.assertEqual(pipeline.get_world_assumption("taughtBy"), "open")

    def test_verify_answer_keeps_correctness_and_completeness_separate(self):
        pipeline = LocalScorePipeline()

        result = pipeline.verify_answer(
            "What are all prerequisites for 123456?",
            "Course 123456 requires 111111.",
        )

        self.assertEqual(result["claim_verification"]["overall_verdict"], "Supported")
        self.assertEqual(result["answer_completeness"]["verdict"], "incomplete")
        self.assertEqual(result["answer_completeness"]["missing"], ["222222"])


if __name__ == "__main__":
    unittest.main()