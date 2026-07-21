import os
import sys
import json
import copy
import random
import logging

# Ensure project root is in path
sys.path.append(os.getcwd())

from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("perturbation_study")

def apply_perturbations(original_courses, deletion_rate, corruption_rate):
    """Returns a perturbed copy of the course catalog."""
    perturbed = copy.deepcopy(original_courses)
    random.seed(42)
    
    for code, course in perturbed.items():
        # 1. Inject Deletions (remove prerequisites or set coordinator to Unknown)
        if random.random() < deletion_rate:
            if "prerequisites" in course:
                course["prerequisites"] = []
            if "coordinator" in course:
                course["coordinator"] = "Unknown"
            if "coordinator_email" in course:
                course["coordinator_email"] = "Unknown"
                
        # 2. Inject Corruptions (modify credits, coordinator names, or school names)
        if random.random() < corruption_rate:
            if "credits" in course:
                course["credits"] = 24 if course.get("credits") == 12 else 12
            if "coordinator" in course and course["coordinator"] != "Unknown":
                course["coordinator"] = course["coordinator"] + "_corrupted"
            if "school" in course and course["school"] != "Unknown":
                course["school"] = course["school"] + "_School_Corrupted"
                
    return perturbed

def main():
    logger.info("Initializing KG Store and Pipeline...")
    store = get_kg_store("data/rmit_graph.json")
    
    # Save a reference to original courses
    original_courses = copy.deepcopy(store.courses)
    
    # Load RMIT test set claims
    test_set_path = "data/rmit_test_set.jsonl"
    if not os.path.exists(test_set_path):
        logger.error("RMIT test set not found.")
        return
        
    test_claims = []
    with open(test_set_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                test_claims.append(json.loads(line))
                
    logger.info(f"Loaded {len(test_claims)} test claims.")
    
    pipeline = VerificationPipeline()
    
    # 1. Pre-decompose all claims once using the unperturbed KG to avoid duplicate LLM calls
    cache_path = "output/cached_decompositions.json"
    cached_decompositions = []
    
    if os.path.exists(cache_path):
        logger.info(f"Loading cached decompositions from {cache_path}...")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_decompositions = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cached decompositions: {e}")
            cached_decompositions = []
            
    if not cached_decompositions or len(cached_decompositions) != len(test_claims):
        logger.info("Pre-decomposing all test claims once using LLM client...")
        cached_decompositions = []
        for idx, item in enumerate(test_claims):
            claims = pipeline.stage_2_decompose(item["raw_claim"])
            cached_decompositions.append(claims)
            if (idx + 1) % 10 == 0 or (idx + 1) == len(test_claims):
                logger.info(f"  Decomposed {idx + 1}/{len(test_claims)} claims.")
        
        # Save cache
        os.makedirs("output", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached_decompositions, f, indent=2)
        logger.info(f"Saved claim decompositions cache to {cache_path}")
            
    # Define sweep rates
    deletion_rates = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    corruption_rates = [0.0, 0.05, 0.1, 0.15, 0.2]
    
    results_del = []
    results_corr = []
    
    logger.info("Starting deletion sweep...")
    for p_del in deletion_rates:
        # Perturb store courses
        store.courses = apply_perturbations(original_courses, p_del, 0.0)
        pipeline.build_entity_index() # Rebuild index for the perturbed state
        
        # Evaluate
        correct = 0
        total = 0
        completeness_scores = []
        
        for idx, item in enumerate(test_claims):
            claims = cached_decompositions[idx]
            
            # Direct verification loop bypassing decomposition
            overall_verdict = "Supported" if claims else "Out-of-scope"
            
            for claim in claims:
                subj_code, relation, obj_val = pipeline.stage_3_map_claim_to_triple(claim)
                if relation == "requiresPrerequisite" and subj_code == obj_val and subj_code is not None:
                    continue
                result = pipeline.stage_4_verify_triple(subj_code, relation, obj_val)
                final_verdict = result["verdict"]
                
                if final_verdict == "Contradicted":
                    overall_verdict = "Contradicted"
                elif final_verdict == "Not-in-KG" and overall_verdict != "Contradicted":
                    overall_verdict = "Not-in-KG"
                elif final_verdict == "Out-of-scope" and overall_verdict not in ["Contradicted", "Not-in-KG"]:
                    overall_verdict = "Out-of-scope"
                    
                if relation and relation not in ["unclassified", "entity_unresolved", "object_unresolved"]:
                    completeness_scores.append(store.estimate_relation_completeness(relation))
                    
            if overall_verdict == item["gold_label"]:
                correct += 1
            total += 1
            
        acc = correct / total if total > 0 else 0.0
        avg_comp = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0
        results_del.append({
            "rate": p_del,
            "accuracy": acc,
            "avg_completeness": avg_comp
        })
        logger.info(f"Deletion Rate: {p_del:.1f} | Verification Accuracy: {acc:.2%} | Avg Est Completeness: {avg_comp:.4f}")
        
    logger.info("Starting corruption sweep...")
    for p_corr in corruption_rates:
        # Perturb store courses
        store.courses = apply_perturbations(original_courses, 0.0, p_corr)
        pipeline.build_entity_index() # Rebuild index for the perturbed state
        
        # Evaluate
        correct = 0
        total = 0
        
        for idx, item in enumerate(test_claims):
            claims = cached_decompositions[idx]
            overall_verdict = "Supported" if claims else "Out-of-scope"
            
            for claim in claims:
                subj_code, relation, obj_val = pipeline.stage_3_map_claim_to_triple(claim)
                if relation == "requiresPrerequisite" and subj_code == obj_val and subj_code is not None:
                    continue
                result = pipeline.stage_4_verify_triple(subj_code, relation, obj_val)
                final_verdict = result["verdict"]
                
                if final_verdict == "Contradicted":
                    overall_verdict = "Contradicted"
                elif final_verdict == "Not-in-KG" and overall_verdict != "Contradicted":
                    overall_verdict = "Not-in-KG"
                elif final_verdict == "Out-of-scope" and overall_verdict not in ["Contradicted", "Not-in-KG"]:
                    overall_verdict = "Out-of-scope"
                    
            if overall_verdict == item["gold_label"]:
                correct += 1
            total += 1
            
        acc = correct / total if total > 0 else 0.0
        results_corr.append({
            "rate": p_corr,
            "accuracy": acc
        })
        logger.info(f"Corruption Rate: {p_corr:.2f} | Verification Accuracy: {acc:.2%}")
        
    # Restore original graph store state
    store.courses = original_courses
    pipeline.build_entity_index()
    
    # Print summary report
    print("\n" + "="*60)
    print("KG PERTURBATION STUDY REPORT")
    print("="*60)
    print("Deletion Sweep (Prerequisite/Coordinator removal):")
    for r in results_del:
        print(f"  Rate: {r['rate']:.1%} -> Accuracy: {r['accuracy']:.2%} | Avg Completeness: {r['avg_completeness']:.4f}")
        
    print("\nCorruption Sweep (Attribute modification/noise):")
    for r in results_corr:
        print(f"  Rate: {r['rate']:.1%} -> Accuracy: {r['accuracy']:.2%}")
    print("="*60 + "\n")
    
    # Save outputs to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "perturbation_study_results.json")
    with open(report_path, "w") as f:
        json.dump({
            "deletions": results_del,
            "corruptions": results_corr
        }, f, indent=2)
    logger.info(f"Saved perturbation study logs to {report_path}")

if __name__ == "__main__":
    main()
