import os
import sys
import json
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure project root is in path
sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_trex")

def normalize(val):
    if not val:
        return ""
    return str(val).lower().strip().replace(" ", "").replace("_", "").replace("-", "")

def match_triple(pred, gold):
    # Match subject, relation, object with normalization
    p_s, p_r, p_o = normalize(pred[0]), normalize(pred[1]), normalize(pred[2])
    g_s, g_r, g_o = normalize(gold[0]), normalize(gold[1]), normalize(gold[2])
    
    # Check match (either exact or substring containment to handle minor naming variants)
    s_match = (p_s == g_s or p_s in g_s or g_s in p_s)
    r_match = (p_r == g_r or p_r in g_r or g_r in p_r)
    o_match = (p_o == g_o or p_o in g_o or g_o in p_o)
    
    return s_match and r_match and o_match

def evaluate_item(item, pipeline):
    text = item["text"]
    gold_triples = item["triples"]
    
    # Run Stage 2 Decompose
    claims = pipeline.stage_2_decompose(text)
    
    pred_triples = []
    for c in claims:
        subj = c.get("subject", "")
        rel = c.get("relation", "")
        obj = c.get("object", "")
        pred_triples.append((subj, rel, obj))
        
    tp = 0
    fp = 0
    fn = 0
    
    matched_gold = set()
    matched_pred = set()
    
    for p_idx, pred in enumerate(pred_triples):
        for g_idx, gold in enumerate(gold_triples):
            if g_idx not in matched_gold and match_triple(pred, gold):
                tp += 1
                matched_gold.add(g_idx)
                matched_pred.add(p_idx)
                break
                
    fp = len(pred_triples) - len(matched_pred)
    fn = len(gold_triples) - len(matched_gold)
    
    precision = tp / len(pred_triples) if pred_triples else (1.0 if not gold_triples else 0.0)
    recall = tp / len(gold_triples) if gold_triples else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "id": item["id"],
        "text": text,
        "gold_triples": gold_triples,
        "pred_triples": pred_triples,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn
    }

def main():
    parser = argparse.ArgumentParser(description="T-REx Extraction-Only Evaluation")
    parser.add_argument("--limit", type=int, default=100, help="Number of items to evaluate")
    parser.add_argument("--workers", type=int, default=10, help="Number of thread workers")
    args = parser.parse_args()
    
    logger.info("Initializing pipeline...")
    pipeline = VerificationPipeline()
    
    data_path = "data/trex_test.jsonl"
    if not os.path.exists(data_path):
        logger.error(f"T-REx dataset not found at {data_path}. Run convert_trex.py first.")
        return
        
    logger.info(f"Loading T-REx data from {data_path}...")
    dataset = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                dataset.append(json.loads(line))
                
    dataset = dataset[:args.limit]
    logger.info(f"Evaluating Stage 2 extraction on {len(dataset)} items...")
    
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(evaluate_item, item, pipeline): item for item in dataset}
        for future in as_completed(futures):
            results.append(future.result())
            
    # Calculate global metrics
    total_precision = sum(r["precision"] for r in results) / len(results) if results else 0.0
    total_recall = sum(r["recall"] for r in results) / len(results) if results else 0.0
    total_f1 = sum(r["f1"] for r in results) / len(results) if results else 0.0
    
    print("\n" + "="*60)
    print("T-REX STAGE 2 DECOMPOSITION / EXTRACTION REPORT")
    print("="*60)
    print(f"Total Evaluated: {len(results)}")
    print(f"Average Precision: {total_precision:.2%}")
    print(f"Average Recall:    {total_recall:.2%}")
    print(f"Average F1-Score:  {total_f1:.2%}")
    print("="*60 + "\n")
    
    # Save output
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "trex_extraction_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "limit": args.limit,
            "average_precision": total_precision,
            "average_recall": total_recall,
            "average_f1": total_f1,
            "details": results
        }, f, indent=2)
    logger.info(f"Saved results details to {out_path}")

if __name__ == "__main__":
    main()
