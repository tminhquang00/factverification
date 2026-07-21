import os
import sys
import json
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter
from eval_harness import compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_concurrent")

def process_single_item(item, pipeline, dataset_name):
    claim = item["text"]
    gold = item["gold_label"]
    triples = item.get("triples", [])
    
    if dataset_name == "factkg":
        pipeline.store.courses = {}
        for s, r, o in triples:
            s_str, r_str, o_str = str(s).strip(), str(r).strip(), str(o).strip()
            if s_str not in pipeline.store.courses:
                pipeline.store.courses[s_str] = {
                    "course_id": s_str, "title": s_str, "credits": 12, "school": "Science",
                    "coordinator": "Unknown", "coordinator_email": "Unknown", "prerequisites": [], "description": ""
                }
            pipeline.store.courses[s_str][r_str] = o_str
        pipeline.build_entity_index()
        
    res = pipeline.verify_statement(claim)
    pred = res["overall_verdict"]
    
    if dataset_name == "factkg":
        if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
            pred = "Contradicted"
        elif pred != "Supported":
            pred = "Contradicted"
    elif dataset_name in ["codex", "metaqa"]:
        if pred == "Out-of-scope":
            pred = "Not-in-KG"
            
    return pred, gold

def evaluate_dataset_concurrent(dataset_name, data, pipeline_path, limit=30, max_workers=10):
    logger.info(f"Evaluating {dataset_name.upper()} on {limit} items with {max_workers} parallel workers...")
    items = data[:limit]
    
    pipeline = VerificationPipeline(kg_path=pipeline_path) if pipeline_path else VerificationPipeline()
    
    predictions = [None] * len(items)
    gold_labels = [None] * len(items)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_single_item, items[i], pipeline, dataset_name): i
            for i in range(len(items))
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                pred, gold = future.result()
                predictions[idx] = pred
                gold_labels[idx] = gold
            except Exception as e:
                logger.error(f"Error evaluating item {idx}: {e}")
                predictions[idx] = "Not-in-KG"
                gold_labels[idx] = items[idx]["gold_label"]
                
    accuracy, class_metrics, ci_lower, ci_upper = compute_metrics(predictions, gold_labels)
    
    covered_indices = [i for i, p in enumerate(predictions) if p in ["Supported", "Contradicted"]]
    coverage = len(covered_indices) / len(predictions) if predictions else 0.0
    covered_correct = sum(1 for i in covered_indices if predictions[i] == gold_labels[i])
    selective_acc = covered_correct / len(covered_indices) if covered_indices else 0.0
    
    return {
        "dataset": dataset_name,
        "n": len(items),
        "accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "coverage": coverage,
        "selective_accuracy": selective_acc
    }

def main():
    results = {}
    
    # 1. CoDEx
    codex_adapter = CoDExAdapter()
    results["codex"] = evaluate_dataset_concurrent("codex", codex_adapter.load_data(), "data/codex_graph.json", limit=30)
    
    # 2. MetaQA
    metaqa_adapter = MetaQAAdapter()
    results["metaqa"] = evaluate_dataset_concurrent("metaqa", metaqa_adapter.load_data(), "data/metaqa_graph.json", limit=30)
    
    # 3. FactKG
    factkg_adapter = FactKGAdapter()
    results["factkg"] = evaluate_dataset_concurrent("factkg", factkg_adapter.load_data(), None, limit=30)
    
    # 4. RMIT
    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    claim_str = item.get("raw_claim", item.get("text"))
                    rmit_data.append({"text": claim_str, "gold_label": g_lbl, "triples": item.get("triples", [])})
    if rmit_data:
        results["rmit"] = evaluate_dataset_concurrent("rmit", rmit_data, "data/rmit_graph.json", limit=30)
        
    print("\n" + "="*70)
    print("ENHANCED PIPELINE CONCURRENT EVALUATION RESULTS")
    print("="*70)
    for ds, res in results.items():
        print(f"Dataset: {ds.upper():<8} | E2E Accuracy: {res['accuracy']:.2%} (95% CI: [{res['ci_95'][0]:.2%}, {res['ci_95'][1]:.2%}]) | Coverage: {res['coverage']:.2%} | Selective Acc: {res['selective_accuracy']:.2%}")
    print("="*70 + "\n")
    
    os.makedirs("output", exist_ok=True)
    with open("output/enhanced_concurrent_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
