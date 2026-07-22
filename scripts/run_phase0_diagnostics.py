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
from adapters.catalog2_adapter import Catalog2Adapter
from eval_harness import compute_metrics, run_pipeline_verification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase0_diagnostics")

def run_e01_shuffled_kg(dataset_name, adapter, pipeline, limit=500):
    logger.info(f"Running E0.1 Shuffled-KG Control for {dataset_name.upper()} (limit={limit})...")
    data = adapter.load_data()[:limit]
    
    all_triples = []
    for item in data:
        all_triples.extend(item.get("triples", []))
        
    rel_to_objects = {}
    for s, r, o in all_triples:
        rel_to_objects.setdefault(r, []).append(o)
        
    for r in rel_to_objects:
        random.shuffle(rel_to_objects[r])
        
    rel_counters = {r: 0 for r in rel_to_objects}
    predictions = []
    gold_labels = []
    
    for item in data:
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])
        
        shuffled_triples = []
        for s, r, o in triples:
            if r in rel_to_objects and rel_to_objects[r]:
                idx = rel_counters[r] % len(rel_to_objects[r])
                shuffled_o = rel_to_objects[r][idx]
                rel_counters[r] += 1
                shuffled_triples.append((s, r, shuffled_o))
            else:
                shuffled_triples.append((s, r, o))
                
        pred = run_pipeline_verification(claim, shuffled_triples, pipeline, dataset_name)
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
        
    acc, _, ci_low, ci_high = compute_metrics(predictions, gold_labels)
    return {"accuracy": acc, "ci_95": [ci_low, ci_high], "n": len(data)}

def run_e02_chance_floors(data, dataset_name):
    golds = [item["gold_label"] for item in data]
    n = len(golds)
    if n == 0:
        return {}
        
    from collections import Counter
    counts = Counter(golds)
    maj_label = counts.most_common(1)[0][0]
    maj_acc = counts[maj_label] / n
    
    classes = list(counts.keys())
    probs = [counts[c] / n for c in classes]
    strat_acc = sum(p ** 2 for p in probs)
    uniform_acc = 1.0 / len(classes) if classes else 0.0
    
    return {
        "dataset": dataset_name,
        "n": n,
        "majority_label": maj_label,
        "majority_class_accuracy": maj_acc,
        "stratified_random_accuracy": strat_acc,
        "uniform_random_accuracy": uniform_acc
    }

def run_e03_denominator_audit(dataset_name, adapter, pipeline, limit=500):
    data = adapter.load_data()[:limit]
    denominators = []
    completeness_scores = []
    sample_logs = []
    
    for idx, item in enumerate(data):
        triples = item.get("triples", [])
        if dataset_name in ["factkg", "codex", "metaqa"]:
            num_entities = len(set([t[0] for t in triples if len(t) > 0] + [t[2] for t in triples if len(t) > 2]))
            denom = max(1, num_entities)
        else:
            denom = len(pipeline.store.courses) if hasattr(pipeline, "store") and hasattr(pipeline.store, "courses") else 50
        
        comp = adapter.completeness(triples[0][1]) if triples and len(triples[0]) > 1 and hasattr(adapter, "completeness") else 0.95
        denominators.append(denom)
        completeness_scores.append(comp)

        sample_logs.append({
            "sample_id": item.get("id", f"{dataset_name}-{idx}"),
            "denominator": denom,
            "completeness_score": comp
        })

    # Log per-sample details to artifact
    os.makedirs("output/diagnostics", exist_ok=True)
    with open(f"output/diagnostics/{dataset_name}_denominator_log.json", "w", encoding="utf-8") as f:
        json.dump(sample_logs, f, indent=2)
        
    return {
        "mean_denominator": float(np.mean(denominators)),
        "min_denominator": int(np.min(denominators)),
        "max_denominator": int(np.max(denominators)),
        "mean_completeness": float(np.mean(completeness_scores)),
        "log_artifact": f"output/diagnostics/{dataset_name}_denominator_log.json"
    }

def main():
    os.makedirs("output/diagnostics", exist_ok=True)
    random.seed(42)
    
    results = {}
    
    # Adapters & Pipelines
    factkg_adapter = FactKGAdapter()
    factkg_pipeline = VerificationPipeline()
    factkg_data = factkg_adapter.load_data()[:500]
    
    codex_adapter = CoDExAdapter()
    codex_pipeline = VerificationPipeline(kg_path="data/codex_graph.json")
    codex_data = codex_adapter.load_data()[:500]
    
    metaqa_adapter = MetaQAAdapter()
    metaqa_pipeline = VerificationPipeline(kg_path="data/metaqa_graph.json")
    metaqa_data = metaqa_adapter.load_data()[:219]

    cat2_adapter = Catalog2Adapter()
    cat2_pipeline = VerificationPipeline(kg_path="data/catalog2_graph.json")
    cat2_data = cat2_adapter.load_data()[:200]
    
    # E0.1 Shuffled-KG
    results["e01_shuffled_kg"] = {
        "factkg": run_e01_shuffled_kg("factkg", factkg_adapter, factkg_pipeline, limit=500),
        "codex": run_e01_shuffled_kg("codex", codex_adapter, codex_pipeline, limit=500),
        "metaqa": run_e01_shuffled_kg("metaqa", metaqa_adapter, metaqa_pipeline, limit=219),
        "catalog2": run_e01_shuffled_kg("catalog2", cat2_adapter, cat2_pipeline, limit=200)
    }
    
    # E0.2 Chance Floors
    results["e02_chance_floors"] = {
        "factkg": run_e02_chance_floors(factkg_data, "factkg"),
        "codex": run_e02_chance_floors(codex_data, "codex"),
        "metaqa": run_e02_chance_floors(metaqa_data, "metaqa"),
        "catalog2": run_e02_chance_floors(cat2_data, "catalog2")
    }
    
    # E0.3 Denominator Audit
    results["e03_denominator_audit"] = {
        "factkg": run_e03_denominator_audit("factkg", factkg_adapter, factkg_pipeline, limit=500),
        "codex": run_e03_denominator_audit("codex", codex_adapter, codex_pipeline, limit=500),
        "metaqa": run_e03_denominator_audit("metaqa", metaqa_adapter, metaqa_pipeline, limit=219),
        "catalog2": run_e03_denominator_audit("catalog2", cat2_adapter, cat2_pipeline, limit=200)
    }
    
    with open("output/diagnostics/phase0_diagnostics_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    logger.info("Saved Phase 0 Diagnostic results to output/diagnostics/phase0_diagnostics_results.json")

if __name__ == "__main__":
    main()
