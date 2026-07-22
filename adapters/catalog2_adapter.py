import os
import json
import logging
from typing import Optional, Dict, Any, List
from adapters.kg_adapter import BaseKGAdapter

logger = logging.getLogger("catalog2_adapter")

class Catalog2Adapter(BaseKGAdapter):
    def __init__(self, data_path="data/catalog2_test.jsonl", kg_path="data/catalog2_graph.json"):
        super().__init__(dataset_name="catalog2", profile_path="data/completeness_profiles/catalog2.json")
        self.data_path = data_path
        self.kg_path = kg_path
        self.kg_data = self._load_kg()

    def _load_kg(self) -> Dict[str, Any]:
        if os.path.exists(self.kg_path):
            with open(self.kg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._generate_catalog2_kg()

    def _generate_catalog2_kg(self) -> Dict[str, Any]:
        logger.info(f"Generating Catalog2 graph at {self.kg_path}")
        kg = {}
        for i in range(1, 101):
            code = f"MED{100 + i}"
            kg[code] = {
                "name": f"Clinical Pharmacology {i}",
                "credits": 12 if i % 2 == 0 else 6,
                "offered_terms": ["Semester 1"] if i % 3 == 0 else ["Semester 1", "Semester 2"],
                "prerequisites": [f"MED{100 + i - 1}"] if i > 1 else [],
                "taught_by": [f"Dr. Staff_{i % 10}"]
            }
        os.makedirs(os.path.dirname(self.kg_path), exist_ok=True)
        with open(self.kg_path, "w", encoding="utf-8") as f:
            json.dump(kg, f, indent=2)
        return kg

    def load_data(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.data_path):
            logger.info(f"Loading Catalog2 data from {self.data_path}")
            data = []
            with open(self.data_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
            return data

        return self._generate_catalog2_dataset()

    def _generate_catalog2_dataset(self) -> List[Dict[str, Any]]:
        logger.info(f"Generating Catalog2 benchmark dataset at {self.data_path}")
        records = []
        for i in range(1, 201):
            code = f"MED{100 + (i % 80) + 1}"
            if i % 3 == 1:
                records.append({
                    "id": f"cat2-{i}",
                    "text": f"Course {code} worth 12 credits has prerequisite MED101.",
                    "gold_label": "Supported",
                    "reasoning_type": "conjunction",
                    "triples": [[code, "hasCreditValue", "12"], [code, "requiresPrerequisite", "MED101"]]
                })
            elif i % 3 == 2:
                records.append({
                    "id": f"cat2-{i}",
                    "text": f"Course {code} is worth 48 credits.",
                    "gold_label": "Contradicted",
                    "reasoning_type": "one-hop",
                    "triples": [[code, "hasCreditValue", "48"]]
                })
            else:
                records.append({
                    "id": f"cat2-{i}",
                    "text": f"Course MED999 is taught by Dr. Unknown.",
                    "gold_label": "Not-in-KG",
                    "reasoning_type": "one-hop",
                    "triples": [["MED999", "taughtBy", "Dr. Unknown"]]
                })

        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "w", encoding="utf-8") as f:
            for item in records:
                f.write(json.dumps(item) + "\n")
        return records

    def link_entity(self, surface: str, context: Optional[dict] = None) -> Optional[str]:
        for code in self.kg_data.keys():
            if code in surface:
                return code
        return None

    def map_relation(self, surface: str, subject: Optional[str] = None) -> Optional[str]:
        s = surface.lower()
        if "credit" in s:
            return "hasCreditValue"
        if "prereq" in s or "requires" in s:
            return "requiresPrerequisite"
        if "taught" in s or "instructor" in s:
            return "taughtBy"
        return None
