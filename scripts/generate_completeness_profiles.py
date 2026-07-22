import os
import sys
import json
import logging

sys.path.append(os.getcwd())

from adapters.kg_adapter import build_offline_completeness_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_completeness_profiles")

def main():
    os.makedirs("data/completeness_profiles", exist_ok=True)
    
    # 1. RMIT Graph
    if os.path.exists("data/rmit_graph.json"):
        with open("data/rmit_graph.json", "r", encoding="utf-8") as f:
            rmit_data = json.load(f)
        build_offline_completeness_profile("rmit", rmit_data, "data/completeness_profiles/rmit.json")
        
    # 2. CoDEx Graph
    if os.path.exists("data/codex_graph.json"):
        with open("data/codex_graph.json", "r", encoding="utf-8") as f:
            codex_data = json.load(f)
        build_offline_completeness_profile("codex", codex_data, "data/completeness_profiles/codex.json")
        
    # 3. MetaQA Graph
    if os.path.exists("data/metaqa_graph.json"):
        with open("data/metaqa_graph.json", "r", encoding="utf-8") as f:
            metaqa_data = json.load(f)
        build_offline_completeness_profile("metaqa", metaqa_data, "data/completeness_profiles/metaqa.json")

if __name__ == "__main__":
    main()
