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

def generate_rmit_dataset(kg_path="data/rmit_graph.json", output_path="data/rmit_test_set.jsonl", num_samples_per_type=6):
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
    
    dataset = []
    
    # Helper to append with counter-evidence or metadata
    def add_sample(reasoning, gold, text, triples):
        # We paraphrase using the LLM client
        logger.info(f"Generating [{reasoning} - {gold}]: {text}")
        paraphrased = paraphrase_claim(text, llm_client)
        dataset.append({
            "id": f"rmit-{reasoning}-{gold.lower()}-{len(dataset)}",
            "dataset": "rmit_handbook",
            "input_type": "response",
            "text": paraphrased,
            "raw_claim": text,
            "gold_label": gold,
            "reasoning_type": reasoning,
            "triples": triples
        })

    # 1. ONE-HOP GENERATION
    # Supported: Course credit points
    for c in random.sample(courses, min(num_samples_per_type // 2, len(courses))):
        text = f"Course {c['course_id']} ({c['title']}) is worth {c['credits']} credit points."
        triples = [[c["course_id"], "hasCreditValue", str(c["credits"])]]
        add_sample("one-hop", "Supported", text, triples)
        
    # Contradicted: Mismatching credit points
    for c in random.sample(courses, min(num_samples_per_type // 2, len(courses))):
        wrong_credits = 24 if c["credits"] == 12 else 12
        text = f"Course {c['course_id']} ({c['title']}) is worth {wrong_credits} credit points."
        triples = [[c["course_id"], "hasCreditValue", str(c["credits"])]]
        add_sample("one-hop", "Contradicted", text, triples)

    # 2. CONJUNCTION GENERATION
    # Supported: Course prerequisites + school
    for c in random.sample(courses_with_prereqs, min(num_samples_per_type // 2, len(courses_with_prereqs))):
        pr = c["prerequisites"][0]
        text = f"Course {c['course_id']} requires {pr['course_id']} ({pr['title']}) and is offered by the School of {c['school']}."
        triples = [
            [c["course_id"], "requiresPrerequisite", pr["course_id"]],
            [c["course_id"], "partOfSchool", c["school"]]
        ]
        add_sample("conjunction", "Supported", text, triples)
        
    # Contradicted: Course prerequisite + wrong school
    for c in random.sample(courses_with_prereqs, min(num_samples_per_type // 2, len(courses_with_prereqs))):
        pr = c["prerequisites"][0]
        wrong_school = "Business" if c["school"] != "Business" else "Science"
        text = f"Course {c['course_id']} requires {pr['course_id']} ({pr['title']}) and is offered by the School of {wrong_school}."
        triples = [
            [c["course_id"], "requiresPrerequisite", pr["course_id"]],
            [c["course_id"], "partOfSchool", c["school"]]
        ]
        add_sample("conjunction", "Contradicted", text, triples)

    # 3. EXISTENCE GENERATION
    # Supported: Course coordinator email
    for c in random.sample(courses, min(num_samples_per_type // 2, len(courses))):
        coord = c["coordinator"]
        email = c["coordinator_email"]
        if coord != "Unknown" and email != "Unknown":
            text = f"There exists a coordinator named {coord} with email {email} in the RMIT catalogue."
            triples = [[c["course_id"], "taughtBy", coord], [coord, "email", email]]
            add_sample("existence", "Supported", text, triples)
            
    # Contradicted: Fake coordinator email
    for c in random.sample(courses, min(num_samples_per_type // 2, len(courses))):
        coord = c["coordinator"]
        if coord != "Unknown":
            text = f"There exists a coordinator named {coord} with email fake_address@rmit.edu.au in the RMIT catalogue."
            triples = [[c["course_id"], "taughtBy", coord], [coord, "email", c["coordinator_email"]]]
            add_sample("existence", "Contradicted", text, triples)

    # 4. MULTI-HOP GENERATION
    # Supported: Transitive prerequisites (A -> B -> C)
    if multi_hop_candidates:
        for A, B, B_details, pp in random.sample(multi_hop_candidates, min(num_samples_per_type // 2, len(multi_hop_candidates))):
            text = f"The prerequisite course of {A['course_id']} ({A['title']}) requires course {pp} as a prerequisite."
            triples = [
                [A["course_id"], "requiresPrerequisite", B["course_id"]],
                [B["course_id"], "requiresPrerequisite", pp]
            ]
            add_sample("multi-hop", "Supported", text, triples)
            
        # Contradicted: Transitive prerequisite mismatch
        for A, B, B_details, pp in random.sample(multi_hop_candidates, min(num_samples_per_type // 2, len(multi_hop_candidates))):
            wrong_pp = "001034" if pp != "001034" else "001123"
            text = f"The prerequisite course of {A['course_id']} ({A['title']}) requires course {wrong_pp} as a prerequisite."
            triples = [
                [A["course_id"], "requiresPrerequisite", B["course_id"]],
                [B["course_id"], "requiresPrerequisite", pp]
            ]
            add_sample("multi-hop", "Contradicted", text, triples)
    else:
        # Fallback if no multi-hop found
        logger.warning("No multi-hop candidates found. Generating pseudo multi-hop.")

    # 5. NEGATION GENERATION
    # Supported: Course does not require prerequisites
    for c in random.sample(courses_no_prereqs, min(num_samples_per_type // 2, len(courses_no_prereqs))):
        text = f"Course {c['course_id']} ({c['title']}) does not require any prerequisite courses."
        triples = []
        add_sample("negation", "Supported", text, triples)
        
    # Contradicted: Course does not require prerequisites but it actually does
    for c in random.sample(courses_with_prereqs, min(num_samples_per_type // 2, len(courses_with_prereqs))):
        pr = c["prerequisites"][0]
        text = f"Course {c['course_id']} ({c['title']}) does not require any prerequisite courses."
        triples = [[c["course_id"], "requiresPrerequisite", pr["course_id"]]]
        add_sample("negation", "Contradicted", text, triples)

    # 6. NOT-IN-KG VERDICTS
    # Out of scope / Entity unresolved samples (for general verification engine testing)
    for _ in range(num_samples_per_type):
        fake_id = str(random.randint(900000, 999999))
        text = f"Course {fake_id} (Advanced AI Ethics) is offered in Semester 3."
        triples = []
        add_sample("one-hop", "Not-in-KG", text, triples)

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
            
    logger.info(f"Successfully generated and saved {len(dataset)} evaluation samples to {output_path}")

if __name__ == "__main__":
    generate_rmit_dataset(num_samples_per_type=15)
