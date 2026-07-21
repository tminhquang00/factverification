import os
import json
import random
import logging
from kg_store import get_kg_store
from llm_client import get_llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_dataset")

def paraphrase_claim(raw_claim: str, llm_client) -> str:
    """Uses LLM to paraphrase the raw claim into a natural query or statement."""
    system_prompt = (
        "You are an administrative assistant. Paraphrase the provided factual statement into a natural-sounding "
        "query, question, or statement that a university student or administrator might write. "
        "Do not change the core facts, names, or codes. Respond with the paraphrased sentence ONLY."
    )
    prompt = f"Factual Statement: \"{raw_claim}\"\n\nParaphrased:"
    try:
        paraphrased = llm_client.generate(prompt, system_prompt=system_prompt, temperature=0.7, max_tokens=100)
        return paraphrased.strip().strip('"')
    except Exception as e:
        logger.error(f"Failed to paraphrase claim: {e}")
        return raw_claim

import argparse

from concurrent.futures import ThreadPoolExecutor

def generate_rmit_dataset(kg_path="data/rmit_graph.json", output_path="data/rmit_test_set.jsonl", num_samples_per_type=50):
    store = get_kg_store(kg_path)
    llm_client = get_llm_client()
    
    courses = list(store.courses.values())
    if not courses:
        logger.error("No courses found in KG Store. Cannot generate dataset.")
        return
        
    # Filter courses with prerequisites
    courses_with_prereqs = [c for c in courses if c.get("prerequisites")]
    # Filter courses without prerequisites
    courses_no_prereqs = [c for c in courses if not c.get("prerequisites")]
    
    # Find multi-hop candidates (A requires B, and B requires C)
    multi_hop_candidates = []
    for c in courses:
        prereqs = c.get("prerequisites", [])
        for p in prereqs:
            parent_prereqs = store.get_prerequisites(p["course_id"])
            if parent_prereqs:
                for pp in parent_prereqs:
                    multi_hop_candidates.append((c, p, store.get_course(p["course_id"]), pp))
                    
    logger.info(f"Candidates for generation: with prereqs={len(courses_with_prereqs)}, no prereqs={len(courses_no_prereqs)}, multi-hop={len(multi_hop_candidates)}")
    
    raw_samples = []
    
    # Helper to collect raw samples before parallel paraphrasing
    def collect_sample(reasoning, gold, text, triples):
        raw_samples.append({
            "reasoning": reasoning,
            "gold": gold,
            "text": text,
            "triples": triples
        })

    half = num_samples_per_type // 2

    # 1. ONE-HOP GENERATION
    for c in random.choices(courses, k=half):
        text = f"Course {c['course_id']} ({c['title']}) is worth {c['credits']} credit points."
        triples = [[c["course_id"], "hasCreditValue", str(c["credits"])]]
        collect_sample("one-hop", "Supported", text, triples)
        
    for c in random.choices(courses, k=half):
        wrong_credits = 24 if c["credits"] == 12 else 12
        text = f"Course {c['course_id']} ({c['title']}) is worth {wrong_credits} credit points."
        triples = [[c["course_id"], "hasCreditValue", str(c["credits"])]]
        collect_sample("one-hop", "Contradicted", text, triples)

    # 2. CONJUNCTION GENERATION
    pool_pr = courses_with_prereqs if courses_with_prereqs else courses
    for c in random.choices(pool_pr, k=half):
        pr = c["prerequisites"][0] if c.get("prerequisites") else {"course_id": "045682", "title": "Programming Fundamentals"}
        text = f"Course {c['course_id']} requires {pr['course_id']} ({pr['title']}) and is offered by the School of {c['school']}."
        triples = [
            [c["course_id"], "requiresPrerequisite", pr["course_id"]],
            [c["course_id"], "partOfSchool", c["school"]]
        ]
        collect_sample("conjunction", "Supported", text, triples)
        
    for c in random.choices(pool_pr, k=half):
        pr = c["prerequisites"][0] if c.get("prerequisites") else {"course_id": "045682", "title": "Programming Fundamentals"}
        wrong_school = "Business" if c["school"] != "Business" else "Science"
        text = f"Course {c['course_id']} requires {pr['course_id']} ({pr['title']}) and is offered by the School of {wrong_school}."
        triples = [
            [c["course_id"], "requiresPrerequisite", pr["course_id"]],
            [c["course_id"], "partOfSchool", c["school"]]
        ]
        collect_sample("conjunction", "Contradicted", text, triples)

    # 3. EXISTENCE GENERATION
    coord_courses = [c for c in courses if c.get("coordinator") != "Unknown" and c.get("coordinator_email") != "Unknown"]
    if not coord_courses:
        coord_courses = courses
    for c in random.choices(coord_courses, k=half):
        coord = c["coordinator"]
        email = c["coordinator_email"]
        text = f"There exists a coordinator named {coord} with email {email} in the RMIT catalogue."
        triples = [[c["course_id"], "taughtBy", coord], [coord, "email", email]]
        collect_sample("existence", "Supported", text, triples)
            
    for c in random.choices(coord_courses, k=half):
        coord = c["coordinator"]
        text = f"There exists a coordinator named {coord} with email fake_address@rmit.edu.au in the RMIT catalogue."
        triples = [[c["course_id"], "taughtBy", coord], [coord, "email", c["coordinator_email"]]]
        collect_sample("existence", "Contradicted", text, triples)

    # 4. MULTI-HOP GENERATION
    if multi_hop_candidates:
        for A, B, B_details, pp in random.choices(multi_hop_candidates, k=half):
            text = f"The prerequisite course of {A['course_id']} ({A['title']}) requires course {pp} as a prerequisite."
            triples = [
                [A["course_id"], "requiresPrerequisite", B["course_id"]],
                [B["course_id"], "requiresPrerequisite", pp]
            ]
            collect_sample("multi-hop", "Supported", text, triples)
            
        for A, B, B_details, pp in random.choices(multi_hop_candidates, k=half):
            wrong_pp = "001034" if pp != "001034" else "001123"
            text = f"The prerequisite course of {A['course_id']} ({A['title']}) requires course {wrong_pp} as a prerequisite."
            triples = [
                [A["course_id"], "requiresPrerequisite", B["course_id"]],
                [B["course_id"], "requiresPrerequisite", pp]
            ]
            collect_sample("multi-hop", "Contradicted", text, triples)
    else:
        for c in random.choices(pool_pr, k=num_samples_per_type):
            pr = c["prerequisites"][0] if c.get("prerequisites") else {"course_id": "045682", "title": "Programming Fundamentals"}
            text = f"Course {c['course_id']} requires {pr['course_id']} as prerequisite."
            collect_sample("multi-hop", "Supported", text, [[c["course_id"], "requiresPrerequisite", pr["course_id"]]])

    # 5. NEGATION GENERATION
    pool_no_pr = courses_no_prereqs if courses_no_prereqs else courses
    for c in random.choices(pool_no_pr, k=half):
        text = f"Course {c['course_id']} ({c['title']}) does not require any prerequisite courses."
        triples = []
        collect_sample("negation", "Supported", text, triples)
        
    for c in random.choices(pool_pr, k=half):
        pr = c["prerequisites"][0] if c.get("prerequisites") else {"course_id": "045682", "title": "Programming Fundamentals"}
        text = f"Course {c['course_id']} ({c['title']}) does not require any prerequisite courses."
        triples = [[c["course_id"], "requiresPrerequisite", pr["course_id"]]]
        collect_sample("negation", "Contradicted", text, triples)

    # 6. NOT-IN-KG VERDICTS
    fake_topics = ["Advanced AI Ethics", "Quantum Machine Learning", "Neural Interfaces", "Autonomous Swarm Robotics", "Deep Reinforcement Learning"]
    for i in range(num_samples_per_type):
        fake_id = str(random.randint(900000, 999999))
        topic = fake_topics[i % len(fake_topics)]
        text = f"Course {fake_id} ({topic}) is offered in Semester 3."
        triples = []
        collect_sample("one-hop", "Not-in-KG", text, triples)

    logger.info(f"Paraphrasing {len(raw_samples)} claims concurrently using LLM...")
    
    def process_item(item_tuple):
        idx, sample = item_tuple
        paraphrased = paraphrase_claim(sample["text"], llm_client)
        return {
            "id": f"rmit-{sample['reasoning']}-{sample['gold'].lower()}-{idx}",
            "dataset": "rmit_handbook",
            "input_type": "response",
            "text": paraphrased,
            "raw_claim": sample["text"],
            "gold_label": sample["gold"],
            "reasoning_type": sample["reasoning"],
            "triples": sample["triples"]
        }

    dataset = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_item, enumerate(raw_samples)))
        dataset.extend(results)

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
            
    logger.info(f"Successfully generated and saved {len(dataset)} evaluation samples to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RMIT Evaluation Dataset Generator")
    parser.add_argument("--num-per-type", type=int, default=50, help="Number of samples per reasoning category (50 * 6 = 300 total)")
    args = parser.parse_args()
    
    generate_rmit_dataset(num_samples_per_type=args.num_per_type)

