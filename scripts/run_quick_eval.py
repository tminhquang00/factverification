import os
import sys
import json
import logging
import numpy as np

sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter
from eval_harness import compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("quick_eval")

def evaluate_single_dataset(dataset_name, data_items, kg_path=None, limit=20):
    logger.info(f"Evaluating {dataset_name.upper()} ({limit} items)...")
    pipeline = VerificationPipeline(kg_path=kg_path) if kg_path else VerificationPipeline()
    
    predictions = []
    gold_labels = []
    
    for idx, item in enumerate(data_items[:limit]):
        claim = item.get("raw_claim") or item.get("text")
        gold = item.get("gold_label") or item.get("verdict", "Supported")
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
                
        predictions.append(pred)
        gold_labels.append(gold)
        logger.info(f"[{dataset_name.upper()} {idx+1}/{limit}] Claim: \"{claim[:60]}...\" | Gold: {gold} | Pred: {pred}")
        
    accuracy, class_metrics, ci_lower, ci_upper = compute_metrics(predictions, gold_labels)
    
    covered_indices = [i for i, p in enumerate(predictions) if p in ["Supported", "Contradicted"]]
    coverage = len(covered_indices) / len(predictions) if predictions else 0.0
    covered_correct = sum(1 for i in covered_indices if predictions[i] == gold_labels[i])
    selective_acc = covered_correct / len(covered_indices) if covered_indices else 0.0
    
    return {
        "dataset": dataset_name,
        "n": len(predictions),
        "accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "coverage": coverage,
        "selective_accuracy": selective_acc
    }

def main():
    results = {}
    
    # 1. CoDEx
    codex_adapter = CoDExAdapter()
    results["codex"] = evaluate_single_dataset("codex", codex_adapter.load_data(), "data/codex_graph.json", limit=20)
    
    # 2. MetaQA
    metaqa_adapter = MetaQAAdapter()
    results["metaqa"] = evaluate_single_dataset("metaqa", metaqa_adapter.load_data(), "data/metaqa_graph.json", limit=20)
    
    # 3. FactKG
    factkg_adapter = FactKGAdapter()
    results["factkg"] = evaluate_single_dataset("factkg", factkg_adapter.load_data(), None, limit=20)
    
    # 4. RMIT
    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    claim_str = item.get("raw_claim", item.get("text"))
                    rmit_data.append({"text": claim_str, "raw_claim": claim_str, "gold_label": g_lbl, "triples": item.get("triples", [])})
    if rmit_data:
        results["rmit"] = evaluate_single_dataset("rmit", rmit_data, "data/rmit_graph.json", limit=20)
        
    print("\n" + "="*70)
    print("ENHANCED PIPELINE FINAL ACCURACY SUMMARY")
    print("="*70)
    for ds, res in results.items():
        print(f"Dataset: {ds.upper():<8} | E2E Accuracy: {res['accuracy']:.2%} (95% CI: [{res['ci_95'][0]:.2%}, {res['ci_95'][1]:.2%}]) | Coverage: {res['coverage']:.2%} | Selective Acc: {res['selective_accuracy']:.2%}")
    print("="*70 + "\n")
    
    os.makedirs("output", exist_ok=True)
    with open("output/final_accuracy_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
