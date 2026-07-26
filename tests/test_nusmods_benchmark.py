"""Regression tests for the NUSMods graph and tri-state benchmark.

The properties asserted here are the ones that make a number measured on this benchmark mean
anything. Each test names the failure it exists to catch.
"""

import collections
import json
import unittest
from functools import lru_cache
from pathlib import Path

from kg_store import KGStore
from scripts.build_nusmods_benchmark import build
from verification_pipeline import ONTOLOGY_RELATIONS

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "data" / "nusmods_graph.json"
BENCHMARK_PATH = ROOT / "data" / "nusmods_test.jsonl"
PROFILE_PATH = ROOT / "data" / "completeness_profiles" / "nusmods.json"


@lru_cache(maxsize=1)
def graph():
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def benchmark():
    return [json.loads(line) for line in
            BENCHMARK_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


@lru_cache(maxsize=1)
def store():
    return KGStore(str(GRAPH_PATH))


class GraphSchemaTests(unittest.TestCase):
    """The graph must be shaped the way KGStore and stage 4 read it."""

    def test_every_record_carries_identity_fields(self):
        for code, record in graph().items():
            self.assertEqual(record["course_id"], code, f"{code}: course_id must equal the key")
            self.assertTrue(record["title"], f"{code}: title must be non-empty")

    def test_prerequisites_are_course_id_records(self):
        """KGStore.get_prerequisites reads entry['course_id']; bare strings raised TypeError."""
        for code, record in graph().items():
            for entry in record.get("prerequisites", []):
                self.assertIsInstance(entry, dict, f"{code}: prerequisite entries must be dicts")
                self.assertIn("course_id", entry)

    def test_absent_fields_are_omitted_rather_than_written_empty(self):
        """An empty list satisfies KGStore's occupancy test and would force closed-world routing.

        Writing `"prerequisites": []` on the modules that declare none would report prerequisite
        occupancy as 1.00 instead of the measured 0.31, pinning a mostly-blank relation to CWA.
        """
        for code, record in graph().items():
            for field, value in record.items():
                self.assertNotIn(value, ([], "", {}), f"{code}.{field} was written empty")

    def test_store_reads_the_ontology_fields(self):
        code = next(c for c, r in graph().items() if r.get("credits") and r.get("prerequisites"))
        self.assertEqual(store().get_credits(code), graph()[code]["credits"])
        self.assertEqual(store().get_school(code), graph()[code]["school"])
        self.assertEqual(store().get_prerequisites(code),
                         [p["course_id"] for p in graph()[code]["prerequisites"]])

    def test_measured_occupancy_matches_the_published_profile(self):
        """The profile is a reporting artifact; if it drifts from the graph it misreports routing."""
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))["relation_completeness"]
        for relation in ("hasCreditValue", "partOfSchool", "requiresPrerequisite"):
            self.assertAlmostEqual(store().estimate_relation_occupancy(relation),
                                   profile[relation], places=3, msg=relation)

    def test_benchmark_relations_have_an_explicit_stage_4_branch(self):
        """Relations outside the ontology fall through to 'Unrecognized relation class'."""
        used = {triple[1] for row in benchmark() for triple in row["asserted_triples"]}
        self.assertTrue(used <= ONTOLOGY_RELATIONS, f"unhandled relations: {used - ONTOLOGY_RELATIONS}")


class BenchmarkLabelTests(unittest.TestCase):
    """Every gold label must follow from the graph, independently of the world assumption."""

    def test_supported_rows_assert_only_facts_the_graph_holds(self):
        for row in benchmark():
            if row["gold_label"] != "Supported":
                continue
            for subject, relation, obj in row["asserted_triples"]:
                record = graph().get(subject)
                self.assertIsNotNone(record, f"{row['id']}: subject absent from the graph")
                if relation == "hasCreditValue":
                    self.assertEqual(str(record["credits"]), obj, row["id"])
                elif relation == "partOfSchool":
                    self.assertEqual(record["school"], obj, row["id"])
                elif relation == "requiresPrerequisite":
                    direct = store().get_prerequisites(subject)
                    two_hop = {p for d in direct for p in store().get_prerequisites(d)}
                    if obj == "none":
                        self.assertEqual(direct, [], row["id"])
                    else:
                        self.assertIn(obj, set(direct) | two_hop, row["id"])

    def test_contradicted_rows_conflict_with_a_value_the_graph_holds(self):
        """A Contradicted row must be false under CWA and under OWA alike.

        If the graph simply had no value for the relation, the row's correct label would depend on
        the routing policy, and the benchmark would be scoring the verifier's own configuration.
        """
        for row in benchmark():
            if row["gold_label"] != "Contradicted":
                continue
            conflicts = False
            for subject, relation, obj in row["asserted_triples"]:
                record = graph().get(subject)
                self.assertIsNotNone(record, f"{row['id']}: subject absent from the graph")
                if relation == "hasCreditValue" and str(record.get("credits")) != obj:
                    conflicts = True
                elif relation == "partOfSchool" and record.get("school") != obj:
                    conflicts = True
                elif relation == "requiresPrerequisite" and obj == "none":
                    conflicts = bool(store().get_prerequisites(subject))
            self.assertTrue(conflicts, f"{row['id']}: no asserted triple conflicts with the graph")

    def test_not_in_kg_rows_name_a_module_the_catalog_does_not_have(self):
        for row in benchmark():
            if row["gold_label"] != "Not-in-KG":
                continue
            for subject, _, _ in row["asserted_triples"]:
                self.assertNotIn(subject, graph(), f"{row['id']}: subject exists in the catalog")

    def test_prerequisite_objects_are_resolvable_modules(self):
        """A prerequisite rule may name a retired code; such a row is unverifiable by construction."""
        for row in benchmark():
            if row["gold_label"] != "Supported":
                continue
            for _, relation, obj in row["asserted_triples"]:
                if relation == "requiresPrerequisite" and obj != "none":
                    self.assertIn(obj, graph(), row["id"])


class BenchmarkStructureTests(unittest.TestCase):
    def test_context_triples_are_evidence_not_the_asserted_claim(self):
        """`triples` is shown to the context_llm baseline.

        On a Contradicted row it must hold the graph's true edge, not the sentence's false one —
        otherwise the baseline is handed a context that entails the claim it is asked to check.
        """
        checked = 0
        for row in benchmark():
            if row["gold_label"] != "Contradicted":
                continue
            context = {tuple(t) for t in row["triples"]}
            asserted = {tuple(t) for t in row["asserted_triples"]}
            self.assertTrue(asserted - context, f"{row['id']}: context entails the false claim")
            checked += 1
        self.assertGreater(checked, 0)

    def test_absent_module_rows_carry_no_context(self):
        for row in benchmark():
            if row["gold_label"] == "Not-in-KG":
                self.assertEqual(row["triples"], [], row["id"])

    def test_no_module_appears_in_two_items(self):
        """Repeating a module lets one item's surface form leak into another's decision."""
        subjects = [row["asserted_triples"][0][0] for row in benchmark()]
        duplicates = [s for s, n in collections.Counter(subjects).items() if n > 1]
        self.assertEqual(duplicates, [])

    def test_majority_class_floor_leaves_room_to_measure(self):
        labels = collections.Counter(row["gold_label"] for row in benchmark())
        self.assertLess(max(labels.values()) / len(benchmark()), 0.40, labels)
        self.assertEqual(set(labels), {"Supported", "Contradicted", "Not-in-KG"})

    def test_ids_are_unique(self):
        ids = [row["id"] for row in benchmark()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_generation_is_deterministic_under_a_seed(self):
        first = build(graph(), limit=40, seed=99)
        second = build(graph(), limit=40, seed=99)
        self.assertEqual(first, second)


class StoreHardeningTests(unittest.TestCase):
    def test_get_prerequisites_accepts_bare_code_strings(self):
        """Graphs compiled elsewhere store prerequisites as codes; indexing them raised TypeError."""
        store_ = KGStore.__new__(KGStore)
        store_.courses = {"A1000": {"course_id": "A1000", "prerequisites": ["B1000", {"course_id": "C1000"}]}}
        self.assertEqual(store_.get_prerequisites("A1000"), ["B1000", "C1000"])


if __name__ == "__main__":
    unittest.main()
