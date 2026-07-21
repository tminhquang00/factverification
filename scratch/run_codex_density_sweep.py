import os
import sys
import json
import random
import logging
import numpy as np

# Ensure project root is in path
sys.path.append(os.getcwd())

from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline
from adapters.codex_adapter import CoDExAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("codex_density_sweep")

def main():
    logger.info("Initializing KG Store and Pipeline...")
    store = get_kg_store("data/codex_graph.json")
    pipeline = VerificationPipeline("data/codex_graph.json")
    
    # Load CoDEx test set
    adapter = CoDExAdapter()
    test_data = adapter.load_data()
    if not test_data:
        logger.error("Empty CoDEx test set. Run convert_codex.py first.")
        return
        
    # Limit test items for faster execution
    random.seed(42)
    random.shuffle(test_data)
    test_data = test_data[:100]
    logger.info(f"Loaded {len(test_data)} claims for sweep evaluation")
    
    # 1. Compute empirical density for all CoDEx relations in the graph
    relations = ["capital", "birthPlace", "spouse", "occupation", "country", "founded", "developer", "employer", "director", "author", "child", "instance of", "part of", "member of"]
    empirical_densities = {}
    
    for rel in relations:
        density = store.estimate_relation_completeness(rel)
        empirical_densities[rel] = density
        logger.info(f"Relation: '{rel:<15}' | Empirical Density: {density:.2%}")
        
    # Bin relations:
    # low (< 0.4), medium (0.4 - 0.7), high (> 0.7)
    bins = {
        "low": [r for r, d in empirical_densities.items() if d < 0.4],
        "medium": [r for r, d in empirical_densities.items() if 0.4 <= d <= 0.7],
        "high": [r for r, d in empirical_densities.items() if d > 0.7]
    }
    
    logger.info(f"Bins: low={len(bins['low'])}, medium={len(bins['medium'])}, high={len(bins['high'])}")
    
    # 2. Sweep completeness threshold theta_c
    thresholds = [0.0, 0.25, 0.5, 0.75, 0.85, 1.0]
    results = {t: {b: {"correct": 0, "total": 0} for b in bins} for t in thresholds}
    
    for thresh in thresholds:
        logger.info(f"Sweeping threshold: {thresh}")
        # Override relation completeness lookup with custom threshold
        store.get_relation_completeness = lambda rel, t=thresh: "closed" if store.estimate_relation_completeness(rel) >= t else "open"
        
        for idx, item in enumerate(test_data):
            claim_text = item["text"]
            gold = item["gold_label"]
            
            # Map claim relation to bin
            rel_name = None
            for r in relations:
                if r in claim_text.lower():
                    rel_name = r
                    break
            if not rel_name:
                rel_name = "spouse"  # Default fallback
                
            matched_bin = "low"
            for b_name, b_rels in bins.items():
                if rel_name in b_rels:
                    matched_bin = b_name
                    break
                    
            res = pipeline.verify_statement(claim_text)
            pred = res["overall_verdict"]
            
            # Normalize prediction label
            if pred == "Out-of-scope":
                pred = "Not-in-KG"
                
            is_correct = 1 if pred == gold else 0
            results[thresh][matched_bin]["correct"] += is_correct
            results[thresh][matched_bin]["total"] += 1
            
    # Print sweep report
    print("\n" + "="*80)
    print("ROUTING ACCURACY SWEEP ACROSS EMPIRICAL DENSITY BINS (CoDEx-S)")
    print("="*80)
    print(f"{'Threshold':<12} | {'Low Density (<0.4)':<20} | {'Med Density (0.4-0.7)':<22} | {'High Density (>0.7)':<20}")
    print("-" * 80)
    for thresh in thresholds:
        vals = []
        for b in ["low", "medium", "high"]:
            corr = results[thresh][b]["correct"]
            tot = results[thresh][b]["total"]
            acc = corr / tot if tot > 0 else 1.0
            vals.append(f"{acc:.2%} ({corr}/{tot})")
        print(f"{thresh:<12.2f} | {vals[0]:<20} | {vals[1]:<22} | {vals[2]:<20}")
    print("="*80 + "\n")
    
    # Save results
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    sweep_path = os.path.join(output_dir, "codex_density_sweep_results.json")
    
    # Format serializeable data
    serialized_results = {}
    for t in thresholds:
        serialized_results[str(t)] = {b: results[t][b]["correct"] / max(1, results[t][b]["total"]) for b in bins}
        
    with open(sweep_path, "w", encoding="utf-8") as f:
        json.dump(serialized_results, f, indent=2)
    logger.info(f"Saved CoDEx density sweep results to {sweep_path}")

if __name__ == "__main__":
    main()
