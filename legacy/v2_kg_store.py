import os
import json
import logging

logger = logging.getLogger("kg_store")

class KGStore:
    def __init__(self, graph_json_path="data/rmit_graph.json"):
        self.graph_json_path = graph_json_path
        self.courses = {}
        self.load_graph()
        
        # Schema definition: relation completeness declarations
        # 'closed': Complete. If fact is not present in graph, it is false (Contradicted).
        # 'open': Incomplete. If fact is not present, it is unknown (Not-in-KG).
        self.relations_completeness = {
            "requiresPrerequisite": "closed",
            "hasCreditValue": "closed",
            "offeredInTerm": "closed",
            "taughtBy": "open",
            "governedBy": "open"
        }

    def load_graph(self):
        if os.path.exists(self.graph_json_path):
            try:
                with open(self.graph_json_path, "r", encoding="utf-8") as f:
                    self.courses = json.load(f)
                logger.info(f"Loaded {len(self.courses)} courses into KG Store from {self.graph_json_path}")
            except Exception as e:
                logger.error(f"Failed to load KG JSON: {e}")
                self.courses = {}
        else:
            logger.warning(f"No compiled Knowledge Graph found at {self.graph_json_path}. Please run parse_handbook.py first.")
            self.courses = {}

    def get_course(self, course_id: str) -> dict:
        return self.courses.get(course_id)

    def has_course(self, course_id: str) -> bool:
        return course_id in self.courses

    def get_prerequisites(self, course_id: str) -> list:
        course = self.get_course(course_id)
        if course:
            return [p["course_id"] for p in course.get("prerequisites", [])]
        return []

    def has_prerequisite(self, course_id: str, prereq_id: str) -> bool:
        return prereq_id in self.get_prerequisites(course_id)

    def get_credits(self, course_id: str) -> int:
        course = self.get_course(course_id)
        if course:
            return course.get("credits", 12)
        return None

    def get_school(self, course_id: str) -> str:
        course = self.get_course(course_id)
        if course:
            return course.get("school", "Unknown")
        return None

    def get_coordinator(self, course_id: str) -> dict:
        course = self.get_course(course_id)
        if course:
            return {
                "name": course.get("coordinator", "Unknown"),
                "email": course.get("coordinator_email", "Unknown")
            }
        return None

    def get_relation_completeness(self, relation: str) -> str:
        return self.relations_completeness.get(relation, "open")

# Singleton instance
_kg_store_instance = None

def get_kg_store(graph_json_path="data/rmit_graph.json") -> KGStore:
    global _kg_store_instance
    if _kg_store_instance is None:
        _kg_store_instance = KGStore(graph_json_path)
    return _kg_store_instance
