import os
import sys
import json
import random
import logging
import copy

# Ensure project root is in path
sys.path.append(os.getcwd())

from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline
from adapters.codex_adapter import CoDExAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("codex_perturbation")

def run_evaluation(pipeline, test_data):
    correct = 0
    total = len(test_data)
    for item in test_data:
        claim_text = item["text"]
        gold = item["gold_label"]
        res = pipeline.verify_statement(claim_text)
        pred = res["overall_verdict"]
        
        # Normalize prediction label
        if pred == "Out-of-scope":
            pred = "Not-in-KG"
            
        if pred == gold:
            correct += 1
    return correct / total if total > 0 else 0.0

def main():
    logger.info("Loading CoDEx test set...")
    adapter = CoDExAdapter()
    test_data = adapter.load_data()
    if not test_data:
        logger.error("Empty CoDEx test set. Run convert_codex.py first.")
        return
        
    random.seed(42)
    random.shuffle(test_data)
    # Evaluate on a representative sample of 50 items for speed and cost
    test_data = test_data[:50]
    logger.info(f"Evaluating perturbation study on {len(test_data)} test items...")
    
    # Save the original courses dict from global store to restore it
    store = get_kg_store("data/codex_graph.json")
    original_courses = copy.deepcopy(store.courses)
    
    pipeline = VerificationPipeline("data/codex_graph.json")
    pipeline.abstention_threshold = 0.5
    
    # Identify all active relation instances that can be deleted/corrupted
    relations = ["capital", "birthPlace", "spouse", "occupation", "country", "founded", "developer", "employer", "director", "author", "child", "instance of", "part of", "member of"]
    
    # Deletion Sweep (0% to 50%)
    deletion_rates = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    deletion_results = []
    
    logger.info("Starting Deletion Sweep...")
    for p in deletion_rates:
        # Restore original state
        store.courses = copy.deepcopy(original_courses)
        
        # Perform deletions
        for code, course in store.courses.items():
            for rel in relations:
                if rel in course and course[rel]:
                    if random.random() < p:
                        # Delete the relation value(s)
                        course[rel] = None
                        
        pipeline.build_entity_index()
        acc = run_evaluation(pipeline, test_data)
        
        # Compute average estimated completeness
        avg_comp = sum(store.estimate_relation_completeness(r) for r in relations) / len(relations)
        deletion_results.append({
            "rate": p,
            "accuracy": acc,
            "avg_completeness": avg_comp
        })
        logger.info(f"Deletion {p:.1%} | E2E Accuracy: {acc:.2%} | Avg Completeness: {avg_comp:.2%}")
        
    # Corruption Sweep (0% to 20%)
    corruption_rates = [0.0, 0.05, 0.1, 0.15, 0.2]
    corruption_results = []
    
    # Gather all entity labels to use for corruption values
    all_entity_labels = []
    for code, course in original_courses.items():
        all_entity_labels.append(course["title"])
        for rel in relations:
            if rel in course and course[rel]:
                if isinstance(course[rel], list):
                    all_entity_labels.extend(course[rel])
                else:
                    all_entity_labels.append(str(course[rel]))
    all_entity_labels = list(set(all_entity_labels))
    
    logger.info("Starting Corruption Sweep...")
    for p in corruption_rates:
        # Restore original state
        store.courses = copy.deepcopy(original_courses)
        
        # Perform corruptions
        for code, course in store.courses.items():
            for rel in relations:
                if rel in course and course[rel]:
                    if random.random() < p:
                        # Corrupt the relation value
                        corrupt_val = random.choice(all_entity_labels)
                        if isinstance(course[rel], list):
                            course[rel] = [corrupt_val]
                        else:
                            course[rel] = corrupt_val
                            
        pipeline.build_entity_index()
        acc = run_evaluation(pipeline, test_data)
        corruption_results.append({
            "rate": p,
            "accuracy": acc
        })
        logger.info(f"Corruption {p:.1%} | E2E Accuracy: {acc:.2%}")
        
    # Restore original store state before finishing
    store.courses = copy.deepcopy(original_courses)
    
    # Save results
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "codex_perturbation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "deletions": deletion_results,
            "corruptions": corruption_results
        }, f, indent=2)
    logger.info(f"Saved perturbation results to {out_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("PERTURBATION STUDY RESULTS (CoDEx-S)")
    print("="*60)
    print("A. Deletion Sweep:")
    for res in deletion_results:
        print(f"  {res['rate']:.0%} Deletions: Accuracy = {res['accuracy']:.2%} | Avg Completeness = {res['avg_completeness']:.2%}")
    print("\nB. Corruption Sweep:")
    for res in corruption_results:
        print(f"  {res['rate']:.0%} Corruption: Accuracy = {res['accuracy']:.2%}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
