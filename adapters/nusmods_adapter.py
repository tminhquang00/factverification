import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from adapters.kg_adapter import BaseKGAdapter

logger = logging.getLogger("nusmods_adapter")

MODULE_CODE_REGEX = re.compile(r"\b([A-Z]{2,4}\d{4}[A-Z]*)\b")


class NusmodsAdapter(BaseKGAdapter):
    """Loader for the NUS module catalog benchmark.

    The graph is compiled by `scripts/parse_nusmods.py` in the field names the pipeline already
    dispatches on, so this adapter maps relation surface forms onto the same ontology RMIT uses
    (`hasCreditValue`, `partOfSchool`, `requiresPrerequisite`) rather than introducing a parallel
    NUS-specific relation set that stage 4 has no branch for.
    """

    def __init__(self, data_path: str = "data/nusmods_test.jsonl",
                 kg_path: str = "data/nusmods_graph.json"):
        super().__init__(dataset_name="nusmods",
                         profile_path="data/completeness_profiles/nusmods.json")
        self.data_path = data_path
        self.kg_path = kg_path
        self.kg_data = self._load_kg()

    def _load_kg(self) -> Dict[str, Any]:
        if os.path.exists(self.kg_path):
            with open(self.kg_path, "r", encoding="utf-8") as handle:
                graph = json.load(handle)
            logger.info(f"Loaded {len(graph)} NUS modules from {self.kg_path}")
            return graph
        logger.warning(f"NUSMods graph not found at {self.kg_path}. Run scripts/parse_nusmods.py.")
        return {}

    def load_data(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.data_path):
            logger.warning(f"NUSMods benchmark not found at {self.data_path}. "
                           "Run scripts/build_nusmods_benchmark.py.")
            return []
        logger.info(f"Loading NUSMods benchmark from {self.data_path}")
        with open(self.data_path, "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def completeness(self, relation_id: str) -> float:
        """Reads the measured occupancy written by scripts/parse_nusmods.py.

        The profile nests its numbers under `relation_completeness`, unlike the flat profiles the
        base class expects, so the lookup is overridden here rather than reshaping the file.
        """
        table = self.profiles.get("relation_completeness", self.profiles)
        return table.get(relation_id, 0.95)

    def link_entity(self, surface: str, context: Optional[dict] = None) -> Optional[str]:
        if not surface:
            return None
        match = MODULE_CODE_REGEX.search(str(surface).upper())
        if match and match.group(1) in self.kg_data:
            return match.group(1)

        target = str(surface).strip().lower()
        for code, record in self.kg_data.items():
            if code.lower() == target or str(record.get("title", "")).lower() == target:
                return code
        return None

    def map_relation(self, surface: str, subject: Optional[str] = None) -> Optional[str]:
        text = str(surface or "").lower()
        if "credit" in text or "mc" in text or "modular" in text:
            return "hasCreditValue"
        if "prereq" in text or "require" in text:
            return "requiresPrerequisite"
        # Faculty and school both land on partOfSchool: the graph stores the NUSMods `faculty`
        # value in the `school` field, which is the field stage 4's partOfSchool branch reads.
        if "faculty" in text or "school" in text or "offered by" in text:
            return "partOfSchool"
        if "department" in text or "dept" in text:
            return "department"
        if "preclu" in text:
            return "preclusions"
        if "semester" in text or "term" in text:
            return "semesters"
        return None
