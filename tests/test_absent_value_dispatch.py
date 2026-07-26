import json
import tempfile
import unittest
from pathlib import Path

from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline


def _store_with(record, key=None):
    """A KGStore over a single entity, written to a temp graph."""
    entity_key = key or record.get("course_id", "Q7604")
    temp_dir = tempfile.mkdtemp()
    graph_path = Path(temp_dir) / "graph.json"
    graph_path.write_text(json.dumps({entity_key: record}), encoding="utf-8")
    return get_kg_store(str(graph_path))


class AccessorAbsenceTests(unittest.TestCase):
    """The store must report absence as absence, not as a plausible default.

    get_credits() defaulted to 12 and get_school() to 'Unknown' whenever the field was missing.
    Combined with converters that injected `credits: 12` into every public-benchmark entity, a
    claim that Leonhard Euler is worth 12 credit points was reported Supported.
    """

    def test_missing_credits_is_none_not_twelve(self):
        store = _store_with({"course_id": "Q7604", "title": "Leonhard Euler"})
        self.assertIsNone(store.get_credits("Q7604"))

    def test_present_credits_are_returned(self):
        store = _store_with({"course_id": "Q7604", "title": "x", "credits": 24})
        self.assertEqual(store.get_credits("Q7604"), 24)

    def test_missing_school_is_none_not_unknown(self):
        store = _store_with({"course_id": "Q7604", "title": "Leonhard Euler"})
        self.assertIsNone(store.get_school("Q7604"))

    def test_unknown_placeholder_school_is_treated_as_absent(self):
        store = _store_with({"course_id": "Q7604", "title": "x", "school": "Unknown"})
        self.assertIsNone(store.get_school("Q7604"))

    def test_unknown_coordinator_placeholders_are_treated_as_absent(self):
        store = _store_with({
            "course_id": "Q7604", "title": "x",
            "coordinator": "Unknown", "coordinator_email": "Unknown",
        })
        coord = store.get_coordinator("Q7604")
        self.assertIsNone(coord["name"])
        self.assertIsNone(coord["email"])

    def test_real_coordinator_survives(self):
        store = _store_with({
            "course_id": "004065", "title": "x",
            "coordinator": "Andy Song", "coordinator_email": "andy.song@rmit.edu.au",
        })
        coord = store.get_coordinator("004065")
        self.assertEqual(coord["name"], "Andy Song")
        self.assertEqual(coord["email"], "andy.song@rmit.edu.au")


class AbsentValueDispatchTests(unittest.TestCase):
    """With no value in the graph, the verdict is decided by the world assumption.

    This is the certain-answers case the CWA/OWA machinery exists for: absence is unknown under
    OWA and false under CWA. Comparing the claim against an invented placeholder — the previous
    behaviour — cannot be sound under either.
    """

    def _pipeline(self, record, routing_mode, key=None):
        pipeline = VerificationPipeline.__new__(VerificationPipeline)
        pipeline.store = _store_with(record, key)
        pipeline.routing_mode = routing_mode
        pipeline.cwa_threshold = 0.85
        return pipeline

    def test_absent_credits_are_undetermined_under_owa(self):
        pipeline = self._pipeline({"course_id": "Q7604", "title": "Leonhard Euler"}, "fixed_owa")
        result = pipeline.stage_4_verify_triple("Q7604", "hasCreditValue", 12)

        self.assertEqual(result["verdict"], "Not-in-KG")
        self.assertIn("<absent>", result["evidence"])

    def test_absent_credits_are_contradicted_under_cwa(self):
        pipeline = self._pipeline({"course_id": "Q7604", "title": "Leonhard Euler"}, "fixed_cwa")
        result = pipeline.stage_4_verify_triple("Q7604", "hasCreditValue", 12)

        self.assertEqual(result["verdict"], "Contradicted")
        self.assertIn("<absent>", result["evidence"])

    def test_a_claim_of_twelve_credits_is_no_longer_supported_by_absence(self):
        """The exact fabrication channel: 12 was the injected constant and the accessor default."""
        for mode in ("fixed_owa", "fixed_cwa"):
            pipeline = self._pipeline({"course_id": "Q7604", "title": "Leonhard Euler"}, mode)
            result = pipeline.stage_4_verify_triple("Q7604", "hasCreditValue", 12)
            self.assertNotEqual(result["verdict"], "Supported", f"routing_mode={mode}")

    def test_present_credits_still_verify_normally(self):
        pipeline = self._pipeline(
            {"course_id": "004065", "title": "Programming 1", "credits": 12}, "fixed_owa"
        )
        self.assertEqual(
            pipeline.stage_4_verify_triple("004065", "hasCreditValue", 12)["verdict"], "Supported"
        )
        self.assertEqual(
            pipeline.stage_4_verify_triple("004065", "hasCreditValue", 24)["verdict"], "Contradicted"
        )

    def test_absent_school_dispatches_on_the_world_assumption(self):
        owa = self._pipeline({"course_id": "Q7604", "title": "Euler"}, "fixed_owa")
        cwa = self._pipeline({"course_id": "Q7604", "title": "Euler"}, "fixed_cwa")

        self.assertEqual(owa.stage_4_verify_triple("Q7604", "partOfSchool", "Science")["verdict"],
                         "Not-in-KG")
        self.assertEqual(cwa.stage_4_verify_triple("Q7604", "partOfSchool", "Science")["verdict"],
                         "Contradicted")

    def test_absent_coordinator_dispatches_on_the_world_assumption(self):
        record = {"course_id": "Q7604", "title": "Euler",
                  "coordinator": "Unknown", "coordinator_email": "Unknown"}
        owa = self._pipeline(record, "fixed_owa")
        cwa = self._pipeline(record, "fixed_cwa")

        self.assertEqual(owa.stage_4_verify_triple("Q7604", "taughtBy", "Unknown")["verdict"],
                         "Not-in-KG")
        self.assertEqual(cwa.stage_4_verify_triple("Q7604", "taughtBy", "Unknown")["verdict"],
                         "Contradicted")


if __name__ == "__main__":
    unittest.main()
