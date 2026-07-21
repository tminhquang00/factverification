import os
import sys
import re
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
logger = logging.getLogger("evaluate_direct_benchmarks")

def parse_claim_local(text):
    """Fast regex parse for claim triples."""
    m = re.match(r"The ([a-zA-Z0-9_\s,]+) of (.+) is (.+)\.", text)
    if m:
        return {"subject": m.group(2).strip(), "relation": m.group(1).strip(), "object": m.group(3).strip(), "claim_type": m.group(1).strip()}
        
    m = re.match(r"(.+) is (located in|a member of|married to|part of) (.+)\.", text)
    if m:
        rel_map = {"located in": "country", "a member of": "member of", "married to": "spouse", "part of": "part of"}
        return {"subject": m.group(1).strip(), "relation": rel_map.get(m.group(2), m.group(2)), "object": m.group(3).strip(), "claim_type": m.group(2)}
        
    if " is " in text:
        parts = text.rstrip(".").split(" is ")
        return {"subject": parts[0].strip(), "relation": "unclassified", "object": parts[1].strip(), "claim_type": "unclassified"}
        
    return {"subject": text, "relation": "unclassified", "object": "unclassified", "claim_type": "unclassified"}

def eval_dataset(name, data_items, pipeline, limit=50):
    predictions = []
    gold_labels = []
    
    for item in data_items[:limit]:
        claim_text = item.get("raw_claim") or item.get("text")
        gold = item.get("gold_label") or item.get("verdict", "Supported")
        triples = item.get("triples", [])
        
        if name == "factkg":
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
            
        claim_dict = parse_claim_local(claim_text)
        subj_code, relation, obj_val = pipeline.stage_3_map_claim_to_triple(claim_dict)
        verdict_res = pipeline.stage_4_verify_triple(subj_code, relation, obj_val)
        pred = verdict_res["verdict"]
        
        if name == "factkg":
            if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                pred = "Contradicted"
            elif pred != "Supported":
                pred = "Contradicted"
        elif name in ["codex", "metaqa"]:
            if pred == "Out-of-scope":
                pred = "Not-in-KG"
                
        predictions.append(pred)
        gold_labels.append(gold)
        
    accuracy, class_metrics, ci_lower, ci_upper = compute_metrics(predictions, gold_labels)
    
    covered_indices = [i for i, p in enumerate(predictions) if p in ["Supported", "Contradicted"]]
    coverage = len(covered_indices) / len(predictions) if predictions else 0.0
    covered_correct = sum(1 for i in covered_indices if predictions[i] == gold_labels[i])
    selective_acc = covered_correct / len(covered_indices) if covered_indices else 0.0
    
    return {
        "dataset": name,
        "n": len(predictions),
        "accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "coverage": coverage,
        "selective_accuracy": selective_acc
    }

def main():
    results = {}
    
    # 1. CoDEx
    pipeline_codex = VerificationPipeline(kg_path="data/codex_graph.json")
    codex_adapter = CoDExAdapter()
    results["codex"] = eval_dataset("codex", codex_adapter.load_data(), pipeline_codex, limit=50)
    
    # 2. MetaQA
    pipeline_metaqa = VerificationPipeline(kg_path="data/metaqa_graph.json")
    metaqa_adapter = MetaQAAdapter()
    results["metaqa"] = eval_dataset("metaqa", metaqa_adapter.load_data(), pipeline_metaqa, limit=50)
    
    # 3. FactKG
    pipeline_factkg = VerificationPipeline()
    factkg_adapter = FactKGAdapter()
    results["factkg"] = eval_dataset("factkg", factkg_adapter.load_data(), pipeline_factkg, limit=50)
    
    # 4. RMIT
    pipeline_rmit = VerificationPipeline(kg_path="data/rmit_graph.json")
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
        results["rmit"] = eval_dataset("rmit", rmit_data, pipeline_rmit, limit=50)
        
    print("\n" + "="*70)
    print("DIRECT BENCHMARK EVALUATION RESULTS (BI-ENCODER + GRAPH PATH)")
    print("="*70)
    for ds, res in results.items():
        print(f"Dataset: {ds.upper():<8} | E2E Accuracy: {res['accuracy']:.2%} (95% CI: [{res['ci_95'][0]:.2%}, {res['ci_95'][1]:.2%}]) | Coverage: {res['coverage']:.2%} | Selective Acc: {res['selective_accuracy']:.2%}")
    print("="*70 + "\n")
    
    os.makedirs("output", exist_ok=True)
    with open("output/direct_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
