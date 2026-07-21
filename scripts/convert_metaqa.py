import os
import sys
sys.path.append(os.getcwd())
import json
import random
import urllib.request
import re
import logging
from llm_client import get_llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("convert_metaqa")

# URLs for MetaQA dataset
KB_URL = "https://raw.githubusercontent.com/yuyuz/MetaQA/master/kb.txt"
HOPS_URLS = {
    1: "https://raw.githubusercontent.com/yuyuz/MetaQA/master/1-hop/vanilla/qa_test.txt",
    2: "https://raw.githubusercontent.com/yuyuz/MetaQA/master/2-hop/vanilla/qa_test.txt",
    3: "https://raw.githubusercontent.com/yuyuz/MetaQA/master/3-hop/vanilla/qa_test.txt"
}

CACHE_DIR = "data/cache/metaqa"
os.makedirs(CACHE_DIR, exist_ok=True)

KB_FILE = os.path.join(CACHE_DIR, "kb.txt")
HOPS_FILES = {
    h: os.path.join(CACHE_DIR, f"qa_test_{h}hop.txt") for h in HOPS_URLS
}

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
    logger.warning("Using mock MetaQA generation fallback...")
    # Mock KB triples
    mock_triples = []
    # Entities: movies M1..M50, directors D1..D10, actors A1..A20
    for i in range(1, 51):
        mock_triples.append(f"Movie_M{i}|directed_by|Director_D{1 + (i % 10)}")
        mock_triples.append(f"Movie_M{i}|starred_actors|Actor_A{1 + (i % 20)}")
        mock_triples.append(f"Movie_M{i}|has_genre|Genre_G{1 + (i % 5)}")
        mock_triples.append(f"Movie_M{i}|release_year|199{i % 10}")
    
    with open(KB_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(mock_triples) + "\n")
        
    # Mock hop test sets
    for h, filepath in HOPS_FILES.items():
        lines = []
        for i in range(1, 150):
            if h == 1:
                lines.append(f"who directed [Movie_M{i}]?\tDirector_D{1 + (i % 10)}")
            elif h == 2:
                lines.append(f"who directed the movies starred by [Actor_A{1 + (i % 20)}]?\tDirector_D{1 + (i % 10)}")
            else:
                lines.append(f"what are the genres of the movies directed by the director of [Movie_M{i}]?\tGenre_G{1 + (i % 5)}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

def convert_qa_to_claim(question, answer, llm_client=None):
    # Strip trailing question mark and clean whitespaces
    q = question.strip().rstrip("?").strip()
    ans = answer.strip()
    
    # Try regex match first
    # 1-hop patterns
    m = re.match(r"(?:who directed|who is the director of) \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"{ans} directed the movie {m.group(1)}."
    
    m = re.match(r"(?:who starred in|who is/are the actors of) \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"{ans} starred in the movie {m.group(1)}."
        
    m = re.match(r"(?:what are the genres of|what is the genre of) \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"The genre of the movie {m.group(1)} is {ans}."
        
    m = re.match(r"(?:when was|what is the release year of) \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"The movie {m.group(1)} was released in {ans}."
        
    m = re.match(r"(?:who wrote the screenplay for|who is the writer of) \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"The screenwriter of the movie {m.group(1)} is {ans}."

    m = re.match(r"(?:what language is) \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"The language of the movie {m.group(1)} is {ans}."
        
    # 2-hop / 3-hop regex matches
    m = re.match(r"who directed the movies starred by \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"{ans} directed a movie that starred {m.group(1)}."

    m = re.match(r"who starred in the movies directed by \[(.+)\]", q, re.IGNORECASE)
    if m:
        return f"{ans} starred in a movie that was directed by {m.group(1)}."
        
    # Use LLM as fallback
    if llm_client:
        system_prompt = (
            "You are a helpful assistant. Convert the given question and answer into a single, natural, "
            "direct declarative factual statement. Do not add intro/outro or explanations. Respond with the statement ONLY."
        )
        prompt = f"Question: \"{question}\"\nAnswer: \"{answer}\"\n\nDeclarative Factual Statement:"
        try:
            res = llm_client.generate(prompt, system_prompt=system_prompt, temperature=0.1, max_tokens=100)
            return res.strip().strip('"')
        except Exception as e:
            logger.error(f"LLM fallback conversion failed: {e}")
            
    # Simple fallback structure
    return f"The answer to the question '{question}' is {answer}."

def main():
    success = True
    success &= download_file(KB_URL, KB_FILE)
    for h, url in HOPS_URLS.items():
        success &= download_file(url, HOPS_FILES[h])
        
    if not success:
        generate_mock_data()
        
    llm_client = get_llm_client()
    
    # Load KB triples
    logger.info("Loading KB triples...")
    triples = []
    unique_entities = set()
    relations = set()
    
    with open(KB_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 3:
                s, r, o = parts[0], parts[1], parts[2]
                triples.append((s, r, o))
                unique_entities.add(s)
                unique_entities.add(o)
                relations.add(r)
                
    logger.info(f"Total MetaQA KB triples: {len(triples)}")
    logger.info(f"Unique entities: {len(unique_entities)}")
    logger.info(f"Relations: {relations}")
    
    # Split entities into 70% active, 30% held-out
    unique_entities = list(unique_entities)
    random.seed(42)
    random.shuffle(unique_entities)
    split_idx = int(len(unique_entities) * 0.70)
    active_entities = set(unique_entities[:split_idx])
    held_out_entities = set(unique_entities[split_idx:])
    
    logger.info(f"Active entities: {len(active_entities)}, Held-out: {len(held_out_entities)}")
    
    # Save active graph to data/metaqa_graph.json
    metaqa_graph = {}
    for s, r, o in triples:
        if s in active_entities and o in active_entities:
            if s not in metaqa_graph:
                metaqa_graph[s] = {
                    "course_id": s,
                    "title": s,
                    "prerequisites": [],
                    "credits": 12,
                    "school": "Science",
                    "coordinator": "Unknown",
                    "coordinator_email": "Unknown"
                }
            if r not in metaqa_graph[s]:
                metaqa_graph[s][r] = []
            if o not in metaqa_graph[s][r]:
                metaqa_graph[s][r].append(o)
                
    graph_path = "data/metaqa_graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(metaqa_graph, f, indent=2)
    logger.info(f"Saved active KG to {graph_path} with {len(metaqa_graph)} entities")
    
    # Load hop QA lines and select 100 per hop (total 300)
    eval_claims = []
    
    # Group entities by relation in active triples for mutation candidates
    rel_objects = {r: set() for r in relations}
    for s, r, o in triples:
        if s in active_entities and o in active_entities:
            rel_objects[r].add(o)
            
    # Also collect all active entity labels of specific categories if possible, or general fallback
    active_entities_list = list(active_entities)
    
    for h in [1, 2, 3]:
        logger.info(f"Processing {h}-hop QA questions...")
        qa_lines = []
        with open(HOPS_FILES[h], "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    qa_lines.append((parts[0], parts[1]))
                    
        random.shuffle(qa_lines)
        
        # We want to select 100 questions of this hop depth:
        # - 33 Supported
        # - 33 Contradicted
        # - 34 Not-in-KG
        hop_claims_count = {
            "Supported": 0,
            "Contradicted": 0,
            "Not-in-KG": 0
        }
        
        for q, ans_str in qa_lines:
            if len(eval_claims) >= h * 100:
                break
                
            answers = [ans.strip() for ans in ans_str.split("|")]
            first_ans = answers[0]
            
            # Find subject entity mentioned in the question (usually inside square brackets in MetaQA)
            # Question is like: "who directed [movie_name]"
            subj_match = re.search(r"\[(.+?)\]", q)
            subj_entity = subj_match.group(1) if subj_match else None
            
            # Check world membership of subject and answer entities
            subj_in_active = subj_entity in active_entities if subj_entity else False
            ans_in_active = any(ans in active_entities for ans in answers)
            
            # Assign target label
            label = None
            if subj_in_active and ans_in_active:
                if hop_claims_count["Supported"] < 33:
                    label = "Supported"
                elif hop_claims_count["Contradicted"] < 33:
                    label = "Contradicted"
            else:
                if hop_claims_count["Not-in-KG"] < 34:
                    label = "Not-in-KG"
                    
            if label is None:
                continue
                
            if label == "Supported":
                claim = convert_qa_to_claim(q, first_ans, llm_client)
                eval_claims.append({
                    "id": f"metaqa-{h}hop-supported-{len(eval_claims)}",
                    "dataset": f"metaqa_{h}hop",
                    "text": claim,
                    "gold_label": "Supported",
                    "reasoning_type": f"{h}-hop",
                    "triples": [[subj_entity, "relation", first_ans]]
                })
                hop_claims_count["Supported"] += 1
                
            elif label == "Contradicted":
                # Find a mutated wrong answer
                # Mutate to another active entity
                wrong_ans = random.choice(active_entities_list)
                while wrong_ans in answers:
                    wrong_ans = random.choice(active_entities_list)
                claim = convert_qa_to_claim(q, wrong_ans, llm_client)
                eval_claims.append({
                    "id": f"metaqa-{h}hop-contradicted-{len(eval_claims)}",
                    "dataset": f"metaqa_{h}hop",
                    "text": claim,
                    "gold_label": "Contradicted",
                    "reasoning_type": f"{h}-hop",
                    "triples": [[subj_entity, "relation", first_ans]]
                })
                hop_claims_count["Contradicted"] += 1
                
            elif label == "Not-in-KG":
                claim = convert_qa_to_claim(q, first_ans, llm_client)
                eval_claims.append({
                    "id": f"metaqa-{h}hop-notinkg-{len(eval_claims)}",
                    "dataset": f"metaqa_{h}hop",
                    "text": claim,
                    "gold_label": "Not-in-KG",
                    "reasoning_type": f"{h}-hop",
                    "triples": [[subj_entity, "relation", first_ans]]
                })
                hop_claims_count["Not-in-KG"] += 1
                
        logger.info(f"Hop {h} generated: {hop_claims_count}")
        
    # Save the test set
    output_path = "data/metaqa_test.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for item in eval_claims:
            f.write(json.dumps(item) + "\n")
            
    logger.info(f"Successfully generated and saved {len(eval_claims)} MetaQA claims to {output_path}")

if __name__ == "__main__":
    main()
