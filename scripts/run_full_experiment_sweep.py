import os
import sys
import json
import random
import logging
import numpy as np

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter
from eval_harness import run_pipeline_verification, compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("full_experiment_sweep")

def run_dataset_eval(dataset_name, adapter, pipeline, limit=100):
    logger.info(f"Running full evaluation on {dataset_name.upper()} (limit={limit})...")
    data = adapter.load_data()[:limit]
    
    predictions = []
    gold_labels = []
    results_detail = []
    
    for idx, item in enumerate(data):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])
        
        pred = run_pipeline_verification(claim, triples, pipeline, dataset_name)
        raw_pred = pred
        
        # Label space normalization
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
        results_detail.append({
            "id": item["id"],
            "claim": claim,
            "gold": gold,
            "pred": pred,
            "raw_pred": raw_pred
        })
        
    accuracy, class_metrics, ci_lower, ci_upper = compute_metrics(predictions, gold_labels)
    
    covered_items = [r for r in results_detail if r["raw_pred"] in ["Supported", "Contradicted"]]
    coverage = len(covered_items) / len(results_detail) if results_detail else 0.0
    covered_correct = sum(1 for r in covered_items if r["pred"] == r["gold"])
    selective_accuracy = covered_correct / len(covered_items) if covered_items else 0.0
    
    summary = {
        "dataset": dataset_name,
        "total_evaluated": len(data),
        "e2e_accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "coverage": coverage,
        "selective_accuracy": selective_accuracy
    }
    logger.info(f"==> {dataset_name.upper()} Results: Accuracy = {accuracy:.2%} (95% CI: [{ci_lower:.2%}, {ci_upper:.2%}]), Coverage = {coverage:.2%}")
    return summary

def main():
    results = {}
    
    # 1. CoDEx
    pipeline_codex = VerificationPipeline(kg_path="data/codex_graph.json")
    codex_adapter = CoDExAdapter()
    results["codex"] = run_dataset_eval("codex", codex_adapter, pipeline_codex, limit=100)
    
    # 2. MetaQA
    pipeline_metaqa = VerificationPipeline(kg_path="data/metaqa_graph.json")
    metaqa_adapter = MetaQAAdapter()
    results["metaqa"] = run_dataset_eval("metaqa", metaqa_adapter, pipeline_metaqa, limit=100)
    
    # 3. FactKG
    pipeline_factkg = VerificationPipeline()
    factkg_adapter = FactKGAdapter()
    results["factkg"] = run_dataset_eval("factkg", factkg_adapter, pipeline_factkg, limit=100)
    
    os.makedirs("output", exist_ok=True)
    with open("output/full_experiment_sweep_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    logger.info("Saved full experiment sweep results to output/full_experiment_sweep_results.json")

if __name__ == "__main__":
    main()
