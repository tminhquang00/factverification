import os
import sys
import json
import random
import logging

# Ensure project root is in path
sys.path.append(os.getcwd())

from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("density_sweep")

def main():
    logger.info("Initializing KG Store and Pipeline...")
    store = get_kg_store("data/rmit_graph.json")
    pipeline = VerificationPipeline()
    
    courses = list(store.courses.keys())
    if not courses:
        logger.error("Empty KG Store. Please parse the handbook first.")
        return
        
    random.seed(42)
    
    # 1. Seed 10 relation fields with target densities from 0.1 to 1.0
    densities = {f"density_rel_{i:02d}": i / 10.0 for i in range(1, 11)}
    
    logger.info("Seeding relations in KG store...")
    relation_data = {rel: {} for rel in densities}
    
    # Decouple "reality" from the KG state to test OWA missing facts correctly
    reality_data = {rel: {} for rel in densities}
    
    for rel, p in densities.items():
        # Reality has all facts populated
        for code in courses:
            val = f"Val_{rel}_{code}"
            reality_data[rel][code] = val
            
            # KG only has a sample populated based on density probability
            if random.random() < p:
                store.courses[code][rel] = val
                relation_data[rel][code] = val
            else:
                # Set to None so relation key is present in course dict for CWA/OWA check
                store.courses[code][rel] = None
                    
    logger.info("Relations seeded successfully.")
    
    # 2. Build test cases: 20 per relation
    # - 10 Supported (value in KG)
    # - 5 Contradicted (value in KG, but wrong value queried)
    # - 5 Missing True Facts (value in reality, but not in KG)
    test_cases = {rel: [] for rel in densities}
    
    for rel, p in densities.items():
        kg_populated_codes = [code for code in courses if store.courses[code].get(rel) is not None]
        kg_missing_codes = [code for code in courses if store.courses[code].get(rel) is None]
        
        # Sample supported
        supported_samples = random.sample(kg_populated_codes, min(10, len(kg_populated_codes)))
        for code in supported_samples:
            test_cases[rel].append({
                "subj": code,
                "rel": rel,
                "obj": store.courses[code][rel],
                "gold": "Supported"
            })
            
        # Sample contradicted
        contradicted_samples = random.sample(kg_populated_codes, min(5, len(kg_populated_codes)))
        for code in contradicted_samples:
            test_cases[rel].append({
                "subj": code,
                "rel": rel,
                "obj": "Wrong_Value_Attrib",
                "gold": "Contradicted"
            })
            
        # Sample missing facts (which are true, so OWA verifier should abstain/return Not-in-KG)
        missing_samples = random.sample(kg_missing_codes, min(5, len(kg_missing_codes)))
        for code in missing_samples:
            test_cases[rel].append({
                "subj": code,
                "rel": rel,
                "obj": reality_data[rel][code],
                "gold": "Not-in-KG"  # Since it's missing from KG, the only correct tri-state prediction is Not-in-KG
            })
            
    # 3. Evaluate E2E accuracy of the verifier for different theta_c thresholds
    # We sweep the completeness threshold theta_c and measure overall accuracy on each relation
    thresholds = [0.0, 0.25, 0.5, 0.75, 0.85, 1.0]
    results = {}
    
    for thresh in thresholds:
        results[thresh] = {}
        # Override relation completeness lookup with the custom threshold
        store.get_relation_completeness = lambda rel, t=thresh: "closed" if store.estimate_relation_completeness(rel) >= t else "open"
        
        for rel in densities.keys():
            correct = 0
            total = 0
            for case in test_cases[rel]:
                res = pipeline.stage_4_verify_triple(case["subj"], case["rel"], case["obj"])
                pred = res["verdict"]
                if pred == case["gold"]:
                    correct += 1
                total += 1
            results[thresh][rel] = correct / total if total > 0 else 0.0
            
    # Print results report
    print("\n" + "="*80)
    print("ROUTING ACCURACY SWEEP ACROSS CONTINUOUS DENSITY spectrum (10 Relations)")
    print("="*80)
    
    headers = ["Relation", "Density", "Thresh 0.0", "Thresh 0.25", "Thresh 0.5", "Thresh 0.75", "Thresh 0.85", "Thresh 1.0"]
    print(" | ".join(headers))
    print("-" * 100)
    
    for rel, p in densities.items():
        row_vals = [rel, p]
        for thresh in thresholds:
            row_vals.append(results[thresh][rel])
        print(f"{rel:<12} | {p:<7.1f} | " + " | ".join([f"{v:.2%}" for v in row_vals[2:]]))
        
    print("="*80 + "\n")
    
    # Save the sweep results to json for report integration
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    sweep_path = os.path.join(output_dir, "density_sweep_results.json")
    with open(sweep_path, "w") as f:
        json.dump({str(k): v for k, v in results.items()}, f, indent=2)
    logger.info(f"Saved sweep results to {sweep_path}")

if __name__ == "__main__":
    main()
