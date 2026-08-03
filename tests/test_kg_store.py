import json
import tempfile
import unittest
from pathlib import Path

from kg_store import get_kg_store


class KGStoreIsolationTests(unittest.TestCase):
    def test_get_kg_store_isolates_graphs_and_mutations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first_path = temp_path / "first.json"
            second_path = temp_path / "second.json"
            first_path.write_text(json.dumps({"A": {"title": "First"}}), encoding="utf-8")
            second_path.write_text(json.dumps({"B": {"title": "Second"}}), encoding="utf-8")

            first_store = get_kg_store(str(first_path))
            second_store = get_kg_store(str(second_path))

            self.assertIsNot(first_store, second_store)
            self.assertEqual(set(first_store.courses), {"A"})
            self.assertEqual(set(second_store.courses), {"B"})

            first_store.courses["A"]["title"] = "Changed"
            self.assertEqual(second_store.courses["B"]["title"], "Second")

    def test_relation_occupancy_measures_populated_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "A": {"coordinator": "Dr. Known", "prerequisites": []},
                        "B": {"coordinator": "Unknown", "prerequisites": []},
                    }
                ),
                encoding="utf-8",
            )
            store = get_kg_store(str(graph_path))

            self.assertEqual(store.estimate_relation_occupancy("taughtBy"), 0.5)
            # An explicit empty set is semantically known, but it contains no relation facts.
            # Occupancy measures populated values; declared completeness is a separate signal.
            self.assertEqual(store.estimate_relation_occupancy("requiresPrerequisite"), 0.0)
            self.assertEqual(
                store.estimate_relation_completeness("taughtBy"),
                store.estimate_relation_occupancy("taughtBy"),
            )


if __name__ == "__main__":
    unittest.main()
