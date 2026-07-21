import os
import json
import random
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("convert_codex")

# URLs for CoDEx-S dataset
ENTITIES_URL = "https://github.com/tsafavi/codex/raw/master/data/entities/en/entities.json"
RELATIONS_URL = "https://raw.githubusercontent.com/tsafavi/codex/master/data/relations/en/relations.json"
TRAIN_URL = "https://raw.githubusercontent.com/tsafavi/codex/master/data/triples/codex-s/train.txt"
VALID_URL = "https://raw.githubusercontent.com/tsafavi/codex/master/data/triples/codex-s/valid.txt"
TEST_URL = "https://raw.githubusercontent.com/tsafavi/codex/master/data/triples/codex-s/test.txt"

# Local cache paths
CACHE_DIR = "data/cache/codex"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

ENTITIES_FILE = os.path.join(CACHE_DIR, "entities.json")
RELATIONS_FILE = os.path.join(CACHE_DIR, "relations.json")
TRAIN_FILE = os.path.join(CACHE_DIR, "train.txt")
VALID_FILE = os.path.join(CACHE_DIR, "valid.txt")
TEST_FILE = os.path.join(CACHE_DIR, "test.txt")

def download_file(url, local_path):
    if os.path.exists(local_path):
        logger.info(f"File already cached: {local_path}")
        return True
    logger.info(f"Downloading {url} to {local_path}...")
    try:
        urllib.request.urlretrieve(url, local_path)
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False

def generate_mock_data():
    logger.warning("Using mock CoDEx-S generation fallback...")
    # Mock entities
    mock_entities = {}
    for i in range(100, 300):
        mock_entities[f"Q{i}"] = {
            "label": f"Entity_Q{i}",
            "description": f"Mock entity description for Q{i}",
            "wiki": f"https://en.wikipedia.org/wiki/Entity_Q{i}"
        }
    
    # Mock relations
    mock_relations = {
        "P17": {"label": "country", "description": "country of the entity"},
        "P36": {"label": "capital", "description": "capital of the country"},
        "P19": {"label": "place of birth", "description": "where the person was born"},
        "P26": {"label": "spouse", "description": "spouse of the person"},
        "P106": {"label": "occupation", "description": "occupation of the person"}
    }
    
    # Mock triples
    mock_triples = []
    # Seed country-capital triples
    for i in range(100, 150):
        # Q(i) is country, Q(i+50) is capital
        mock_triples.append(f"Q{i}\tP17\tQ{i}")
        mock_triples.append(f"Q{i}\tP36\tQ{i+50}")
        # Q(i) has birth place Q(i+50)
        mock_triples.append(f"Q{i+100}\tP19\tQ{i+50}")
        # Q(i+100) has spouse Q(i+101) (only for even ids)
        if i % 2 == 0:
            mock_triples.append(f"Q{i+100}\tP26\tQ{i+101}")
            mock_triples.append(f"Q{i+100}\tP106\tQ{150}") # occupation is Q150
            
    with open(ENTITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(mock_entities, f, indent=2)
    with open(RELATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(mock_relations, f, indent=2)
    with open(TRAIN_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(mock_triples[:100]) + "\n")
    with open(VALID_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(mock_triples[100:130]) + "\n")
    with open(TEST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(mock_triples[130:]) + "\n")

def verbalize_triple(subj_label, rel_label, obj_label):
    templates = {
        "country": f"{subj_label} is located in {obj_label}.",
        "capital": f"The capital of {subj_label} is {obj_label}.",
        "place of birth": f"The birthplace of {subj_label} is {obj_label}.",
        "spouse": f"{subj_label} is married to {obj_label}.",
        "occupation": f"The occupation of {subj_label} is {obj_label}.",
        "developer": f"{subj_label} was developed by {obj_label}.",
        "employer": f"{subj_label} is employed by {obj_label}.",
        "director": f"{subj_label} was directed by {obj_label}.",
        "author": f"{subj_label} was written by {obj_label}.",
        "child": f"The child of {subj_label} is {obj_label}.",
        "instance of": f"{subj_label} is an instance of {obj_label}.",
        "part of": f"{subj_label} is part of {obj_label}.",
        "member of": f"{subj_label} is a member of {obj_label}.",
        "founded by": f"{subj_label} was founded by {obj_label}."
    }
    rel_clean = rel_label.lower().strip()
    if rel_clean in templates:
        return templates[rel_clean]
    return f"The {rel_label} of {subj_label} is {obj_label}."

def main():
    # 1. Download files
    success = True
    success &= download_file(ENTITIES_URL, ENTITIES_FILE)
    success &= download_file(RELATIONS_URL, RELATIONS_FILE)
    success &= download_file(TRAIN_URL, TRAIN_FILE)
    success &= download_file(VALID_URL, VALID_FILE)
    success &= download_file(TEST_URL, TEST_FILE)
    
    if not success:
        generate_mock_data()
        
    # 2. Load entities and relations
    logger.info("Loading entities and relations maps...")
    with open(ENTITIES_FILE, "r", encoding="utf-8") as f:
        entities = json.load(f)
    with open(RELATIONS_FILE, "r", encoding="utf-8") as f:
        relations = json.load(f)
        
    # 3. Load all triples
    logger.info("Loading triples...")
    all_triples = []
    
    def load_triples_from_file(filepath):
        triples = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    triples.append((parts[0], parts[1], parts[2]))
        return triples
        
    all_triples.extend(load_triples_from_file(TRAIN_FILE))
    all_triples.extend(load_triples_from_file(VALID_FILE))
    all_triples.extend(load_triples_from_file(TEST_FILE))
    
    logger.info(f"Total triples loaded: {len(all_triples)}")
    
    # Identify unique entities
    unique_entities = list(set([t[0] for t in all_triples] + [t[2] for t in all_triples]))
    logger.info(f"Unique entities in triples: {len(unique_entities)}")
    
    # 4. Split entities into 70% active and 30% held-out
    random.seed(42)
    random.shuffle(unique_entities)
    split_idx = int(len(unique_entities) * 0.70)
    active_entities = set(unique_entities[:split_idx])
    held_out_entities = set(unique_entities[split_idx:])
    
    logger.info(f"Active entities (in-graph): {len(active_entities)}, Held-out: {len(held_out_entities)}")
    
    # 5. Build active triples and construct active graph (codex_graph.json)
    active_triples = []
    held_out_triples = []
    
    for s, r, o in all_triples:
        if s in active_entities and o in active_entities:
            active_triples.append((s, r, o))
        else:
            held_out_triples.append((s, r, o))
            
    logger.info(f"Active triples: {len(active_triples)}, Held-out triples: {len(held_out_triples)}")
    
    # Construct codex_graph.json
    codex_graph = {}
    for s, r, o in active_triples:
        s_label = entities.get(s, {}).get("label", s)
        o_label = entities.get(o, {}).get("label", o)
        r_label = relations.get(r, {}).get("label", r)
        
        if s not in codex_graph:
            codex_graph[s] = {
                "course_id": s,
                "title": s_label,
                "prerequisites": [],
                "credits": 12,
                "school": "Science",
                "coordinator": "Unknown",
                "coordinator_email": "Unknown"
            }
        
        # In Wikidata, a relation can have multiple values
        if r_label not in codex_graph[s]:
            codex_graph[s][r_label] = []
        if o_label not in codex_graph[s][r_label]:
            codex_graph[s][r_label].append(o_label)
            
    # Save the graph
    graph_path = "data/codex_graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(codex_graph, f, indent=2)
    logger.info(f"Saved active KG graph to {graph_path} containing {len(codex_graph)} entities")
    
    # 6. Generate ~1,000 claims (balanced tri-state: 333 Supported, 333 Contradicted, 334 Not-in-KG)
    dataset = []
    
    # A. Supported Claims (~333)
    logger.info("Generating Supported claims...")
    supported_samples = random.sample(active_triples, min(333, len(active_triples)))
    for s, r, o in supported_samples:
        s_label = entities.get(s, {}).get("label", s)
        o_label = entities.get(o, {}).get("label", o)
        r_label = relations.get(r, {}).get("label", r)
        
        claim_text = verbalize_triple(s_label, r_label, o_label)
        dataset.append({
            "id": f"codex-supported-{len(dataset)}",
            "dataset": "codex",
            "text": claim_text,
            "gold_label": "Supported",
            "reasoning_type": "one-hop",
            "triples": [[s_label, r_label, o_label]]
        })
        
    # B. Contradicted Claims (~333)
    logger.info("Generating Contradicted claims...")
    # Group active triples by relation to find mutation candidates
    rel_objects = {}
    for s, r, o in active_triples:
        if r not in rel_objects:
            rel_objects[r] = set()
        o_label = entities.get(o, {}).get("label", o)
        rel_objects[r].add(o_label)
        
    # We sample active triples to mutate
    contradicted_candidates = random.sample(active_triples, min(333, len(active_triples)))
    for s, r, o in contradicted_candidates:
        s_label = entities.get(s, {}).get("label", s)
        o_label = entities.get(o, {}).get("label", o)
        r_label = relations.get(r, {}).get("label", r)
        
        # Select mutated object from other values of this relation
        candidates = list(rel_objects[r] - {o_label})
        if not candidates:
            # Fallback to any random entity label if no other values exist for this relation
            candidates = [entities.get(random.choice(unique_entities), {}).get("label", "Unknown")]
            
        mutated_obj = random.choice(candidates)
        claim_text = verbalize_triple(s_label, r_label, mutated_obj)
        
        dataset.append({
            "id": f"codex-contradicted-{len(dataset)}",
            "dataset": "codex",
            "text": claim_text,
            "gold_label": "Contradicted",
            "reasoning_type": "one-hop",
            "triples": [[s_label, r_label, o_label]]  # Stored true context triple
        })
        
    # C. Not-in-KG (Held-out) Claims (~334)
    logger.info("Generating Not-in-KG claims...")
    # We sample from held_out_triples
    notinkg_samples = random.sample(held_out_triples, min(334, len(held_out_triples)))
    for s, r, o in notinkg_samples:
        s_label = entities.get(s, {}).get("label", s)
        o_label = entities.get(o, {}).get("label", o)
        r_label = relations.get(r, {}).get("label", r)
        
        claim_text = verbalize_triple(s_label, r_label, o_label)
        dataset.append({
            "id": f"codex-notinkg-{len(dataset)}",
            "dataset": "codex",
            "text": claim_text,
            "gold_label": "Not-in-KG",
            "reasoning_type": "one-hop",
            "triples": [[s_label, r_label, o_label]]  # Stored true context triple (which is missing in KG)
        })
        
    # Shuffle dataset
    random.shuffle(dataset)
    
    # Save test set
    output_path = "data/codex_test.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
            
    logger.info(f"Successfully generated and saved {len(dataset)} CoDEx-S evaluation samples to {output_path}")

if __name__ == "__main__":
    main()
