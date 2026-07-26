import os
import json
import logging

logger = logging.getLogger("kg_store")

class KGStore:
    """Thread-safe catalog storage containing graph density estimation and relation lookup logic.
    
    This class handles the parsing and querying of structured RMIT Course Handbook data
    (or any public DBpedia-lite triple set mapped to course fields). Read-only lookup methods
    support concurrent requests, ensuring thread safety during parallel harness executions.
    """
    def __init__(self, graph_json_path="data/rmit_graph.json"):
        """Initializes the KGStore and loads the compiled graph from the JSON path."""
        self.graph_json_path = graph_json_path
        self.courses = {}
        self.load_graph()

    def load_graph(self):
        """Loads the compiled JSON graph database.
        
        Populates self.courses by loading the serialized dictionary from graph_json_path.
        Logs warning or error if file path is missing or load fails.
        """
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
        """Retrieves raw catalog record dict for a given course code.
        
        Args:
            course_id (str): The unique 6-digit course code.
            
        Returns:
            dict: The course attributes dictionary if found, else None.
        """
        return self.courses.get(course_id)

    def has_course(self, course_id: str) -> bool:
        """Verifies if the course code exists in the catalog.
        
        Args:
            course_id (str): The course code to check.
            
        Returns:
            bool: True if the course is registered in the database, else False.
        """
        return course_id in self.courses

    def get_prerequisites(self, course_id: str) -> list:
        """Retrieves list of prerequisite course codes for a course.

        Entries may be either `{"course_id": ...}` records or bare code strings. Graphs compiled
        from different catalogs use both shapes, and indexing a string raised TypeError, taking
        the whole row unscored rather than yielding a verdict.

        Args:
            course_id (str): The unique course code.

        Returns:
            list: List of prerequisite course codes, or an empty list if none are specified.
        """
        course = self.get_course(course_id)
        if not course:
            return []
        prerequisites = []
        for entry in course.get("prerequisites", []) or []:
            code = entry.get("course_id") if isinstance(entry, dict) else entry
            if code:
                prerequisites.append(str(code))
        return prerequisites

    def has_prerequisite(self, course_id: str, prereq_id: str) -> bool:
        """Determines if a specific course is a prerequisite for another course.
        
        Args:
            course_id (str): The target course code.
            prereq_id (str): The prerequisite course code to check.
            
        Returns:
            bool: True if prereq_id is required by course_id, else False.
        """
        return prereq_id in self.get_prerequisites(course_id)

    def get_credits(self, course_id: str) -> int:
        """Retrieves credit value for a course.

        Absence is reported as absence. This accessor used to default to 12 when the field was
        missing, which fabricated a comparable value out of nothing: a claim of "12 credit points"
        against an entity with no credit data was reported Supported. Returning None hands the
        decision to the world-assumption dispatch, which is what decides whether missing data
        means false (CWA) or unknown (OWA).

        Args:
            course_id (str): The unique course code.

        Returns:
            int: The credit points, or None if the course or the field is absent.
        """
        course = self.get_course(course_id)
        if course:
            return course.get("credits")
        return None

    def get_school(self, course_id: str) -> str:
        """Retrieves School name offering the course.

        Returns None rather than 'Unknown' when the field is absent — see get_credits.

        Args:
            course_id (str): The unique course code.

        Returns:
            str: School name (e.g. 'Science'), or None if the course or the field is absent.
        """
        course = self.get_course(course_id)
        if course:
            school = course.get("school")
            return None if school in ("", "Unknown") else school
        return None

    def get_coordinator(self, course_id: str) -> dict:
        """Retrieves coordinator name and contact email for a course.

        'Unknown' placeholders are normalized to None so callers cannot compare against them —
        see get_credits.

        Args:
            course_id (str): The unique course code.

        Returns:
            dict: A dictionary containing 'name' and 'email' keys, either of which may be None.
        """
        course = self.get_course(course_id)
        if course:
            def _present(value):
                return None if value in (None, "", "Unknown") else value

            return {
                "name": _present(course.get("coordinator")),
                "email": _present(course.get("coordinator_email")),
            }
        return None

    def estimate_relation_occupancy(self, relation: str) -> float:
        """Returns the fraction of entity records with a populated field for the relation."""
        if not self.courses:
            return 0.0
            
        # Map ontology relations to actual keys in rmit_graph.json
        field_map = {
            "requiresPrerequisite": "prerequisites",
            "hasCreditValue": "credits",
            "partOfSchool": "school",
            "taughtBy": "coordinator",
            "coordinator": "coordinator",
            "email": "coordinator_email"
        }
        
        key = field_map.get(relation, relation)
        total = len(self.courses)
        present = 0

        for course in self.courses.values():
            if key not in course:
                continue
            value = course.get(key)
            if value is not None and value != "" and value != "Unknown":
                present += 1

        return present / total if total > 0 else 0.0

    def estimate_relation_completeness(self, relation: str) -> float:
        """Compatibility alias for the historical, occupancy-based score API."""
        return self.estimate_relation_occupancy(relation)

    def find_graph_path(self, start_entity: str, target_entity: str, max_depth: int = 3) -> list:
        """Finds paths between start_entity and target_entity up to max_depth in the KG."""
        if not start_entity or not target_entity:
            return []
        start_norm = str(start_entity).strip()
        target_norm = str(target_entity).strip()
        
        if start_norm == target_norm:
            return [[start_norm]]
            
        queue = [(start_norm, [start_norm])]
        visited = {start_norm}
        found_paths = []
        
        while queue:
            curr, path = queue.pop(0)
            if len(path) > max_depth:
                continue
                
            curr_data = self.courses.get(curr, {})
            neighbors = []
            for rel, val in curr_data.items():
                if rel in ["course_id", "title", "credits", "school", "coordinator", "coordinator_email", "prerequisites", "description"]:
                    if rel == "prerequisites" and isinstance(val, list):
                        for p in val:
                            p_id = p.get("course_id") if isinstance(p, dict) else str(p)
                            if p_id:
                                neighbors.append((rel, p_id))
                    continue
                if isinstance(val, list):
                    for v in val:
                        neighbors.append((rel, str(v)))
                elif val is not None:
                    neighbors.append((rel, str(val)))
                    
            for other_id, other_data in self.courses.items():
                if other_id in visited:
                    continue
                for rel, val in other_data.items():
                    if rel in ["course_id", "title", "credits", "school", "coordinator", "coordinator_email", "prerequisites", "description"]:
                        continue
                    if (isinstance(val, list) and curr in [str(v) for v in val]) or str(val) == curr:
                        neighbors.append((f"rev_{rel}", other_id))
                        
            for rel, nxt in neighbors:
                if nxt == target_norm:
                    found_paths.append(path + [nxt])
                    if len(found_paths) >= 3:
                        return found_paths
                elif nxt not in visited and len(path) < max_depth:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
                    
        return found_paths

    def get_relation_completeness(self, relation: str) -> str:
        score = self.estimate_relation_occupancy(relation)
        if score >= 0.85:
            return "closed"
        return "open"

def get_kg_store(graph_json_path="data/rmit_graph.json") -> KGStore:
    """Creates an independent store for the requested graph snapshot."""
    return KGStore(graph_json_path)
