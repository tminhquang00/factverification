import os
import json
import logging
from typing import Protocol, Optional, Dict, Any, List

logger = logging.getLogger("kg_adapter")

class KGAdapter(Protocol):
    def link_entity(self, surface: str, context: Optional[dict] = None) -> Optional[str]:
        ...
        
    def map_relation(self, surface: str, subject: Optional[str] = None) -> Optional[str]:
        ...
        
    def completeness(self, relation_id: str) -> float:
        ...

class BaseKGAdapter:
    def __init__(self, dataset_name: str, profile_path: Optional[str] = None):
        self.dataset_name = dataset_name
        self.profile_path = profile_path or f"data/completeness_profiles/{dataset_name}.json"
        self.profiles: Dict[str, float] = {}
        self.load_profile()
        
    def load_profile(self):
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    self.profiles = json.load(f)
                logger.info(f"Loaded offline completeness profile from {self.profile_path}")
            except Exception as e:
                logger.error(f"Error loading profile {self.profile_path}: {e}")
                self.profiles = {}
        else:
            logger.warning(f"No profile found at {self.profile_path}. Defaulting to 0.95.")
            
    def completeness(self, relation_id: str) -> float:
        return self.profiles.get(relation_id, 0.95 if self.dataset_name != "rmit" else 0.85)

def build_offline_completeness_profile(dataset_name: str, kg_data: Dict[str, Any], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    rel_counts: Dict[str, int] = {}
    total_entities = len(kg_data)
    
    for entity_id, properties in kg_data.items():
        if isinstance(properties, dict):
            for k in properties.keys():
                rel_counts[k] = rel_counts.get(k, 0) + 1
                
    profiles = {}
    for r, count in rel_counts.items():
        profiles[r] = round(min(1.0, count / max(1, total_entities)), 4)
        
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    logger.info(f"Built offline completeness profile for {dataset_name} ({len(profiles)} relations) at {output_path}")
    return profiles
