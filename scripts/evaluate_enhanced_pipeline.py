import os
import sys
import json
import random
import logging
import numpy as np

sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter
from eval_harness import compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_enhanced_pipeline")

def evaluate_dataset_fast(dataset_name, data, pipeline):
    logger.info(f"Evaluating {dataset_name.upper()} on {len(data)} items...")
    predictions = []
    gold_labels = []
    
    for item in data:
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
                
        predictions.append(pred)
        gold_labels.append(gold)
        
    accuracy, class_metrics, ci_lower, ci_upper = compute_metrics(predictions, gold_labels)
    
    # Calculate coverage and selective accuracy
    covered_indices = [i for i, p in enumerate(predictions) if p in ["Supported", "Contradicted"]]
    coverage = len(covered_indices) / len(predictions) if predictions else 0.0
    covered_correct = sum(1 for i in covered_indices if predictions[i] == gold_labels[i])
    selective_acc = covered_correct / len(covered_indices) if covered_indices else 0.0
    
    return {
        "dataset": dataset_name,
        "n": len(data),
        "accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "coverage": coverage,
        "selective_accuracy": selective_acc
    }

def main():
    results = {}
    
    # 1. CoDEx
    codex_adapter = CoDExAdapter()
    codex_data = codex_adapter.load_data()[:40]
    pipeline_codex = VerificationPipeline(kg_path="data/codex_graph.json")
    results["codex"] = evaluate_dataset_fast("codex", codex_data, pipeline_codex)
    
    # 2. MetaQA
    metaqa_adapter = MetaQAAdapter()
    metaqa_data = metaqa_adapter.load_data()[:40]
    pipeline_metaqa = VerificationPipeline(kg_path="data/metaqa_graph.json")
    results["metaqa"] = evaluate_dataset_fast("metaqa", metaqa_data, pipeline_metaqa)
    
    # 3. FactKG
    factkg_adapter = FactKGAdapter()
    factkg_data = factkg_adapter.load_data()[:40]
    pipeline_factkg = VerificationPipeline()
    results["factkg"] = evaluate_dataset_fast("factkg", factkg_data, pipeline_factkg)
    
    # 4. RMIT
    pipeline_rmit = VerificationPipeline(kg_path="data/rmit_graph.json")
    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    rmit_data.append({"text": item.get("raw_claim", item["text"]), "gold_label": g_lbl, "triples": []})
    if rmit_data:
        results["rmit"] = evaluate_dataset_fast("rmit", rmit_data[:40], pipeline_rmit)
        
    print("\n" + "="*60)
    print("ENHANCED PIPELINE EVALUATION SUMMARY")
    print("="*60)
    for ds, res in results.items():
        print(f"Dataset: {ds.upper():<8} | E2E Accuracy: {res['accuracy']:.2%} (95% CI: [{res['ci_95'][0]:.2%}, {res['ci_95'][1]:.2%}]) | Coverage: {res['coverage']:.2%} | Selective Acc: {res['selective_accuracy']:.2%}")
    print("="*60 + "\n")
    
    os.makedirs("output", exist_ok=True)
    with open("output/enhanced_pipeline_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
