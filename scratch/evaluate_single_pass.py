import os
import sys
import json
import numpy as np
from collections import Counter

sys.path.append(os.getcwd())

from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter
from adapters.catalog2_adapter import Catalog2Adapter
from verification_pipeline import VerificationPipeline
from eval_harness import run_pipeline_verification

def compute_single_pass_metrics(predictions, gold_labels):
    n = len(gold_labels)
    unique_labels = ["Supported", "Contradicted", "Not-in-KG"]
    
    cm = {g: {p: 0 for p in unique_labels} for g in unique_labels}
    for p, g in zip(predictions, gold_labels):
        g_key = g if g in cm else "Not-in-KG"
        p_key = p if p in unique_labels else "Not-in-KG"
        cm[g_key][p_key] += 1

    correct = sum(cm[c][c] for c in unique_labels)
    acc = correct / n if n > 0 else 0.0

    f1s = {}
    precisions = {}
    recalls = {}
    
    for c in unique_labels:
        tp = cm[c][c]
        fp = sum(cm[g][c] for g in unique_labels if g != c)
        fn = sum(cm[c][p] for p in unique_labels if p != c)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        
        precisions[c] = float(prec)
        recalls[c] = float(rec)
        f1s[c] = float(f1)
        
    macro_f1 = float(np.mean([f1s[c] for c in unique_labels]))

    total_pred_contra = sum(cm[g]["Contradicted"] for g in unique_labels)
    false_contra = sum(cm[g]["Contradicted"] for g in ["Supported", "Not-in-KG"])
    fcr_pct = (false_contra / total_pred_contra) if total_pred_contra > 0 else 0.0

    gold_contra = sum(cm["Contradicted"][p] for p in unique_labels)
    contra_rec = recalls["Contradicted"]

    return {
        "n": n,
        "accuracy": float(acc),
        "macro_f1": float(macro_f1),
        "confusion_matrix": cm,
        "class_f1s": f1s,
        "class_precisions": precisions,
        "class_recalls": recalls,
        "total_pred_contradictions": total_pred_contra,
        "false_contradictions": false_contra,
        "fcr_fraction": f"{false_contra}/{total_pred_contra}",
        "fcr_pct": float(fcr_pct),
        "gold_contradictions": gold_contra,
        "contradiction_recall": float(contra_rec)
    }

def run_e2_stratified_rmit(data, pipeline):
    sparse_items = []
    for item in data:
        triples = item.get("triples", [])
        rel = triples[0][1] if triples and len(triples[0]) > 1 else ""
        if rel in ["taughtBy", "requiresPrerequisite"]:
            sparse_items.append(item)
            
    stratified_results = {}
    
    for mode in ["dynamic", "fixed_cwa", "fixed_owa"]:
        if mode == "fixed_cwa":
            pipeline.cwa_threshold = 0.0
        elif mode == "fixed_owa":
            pipeline.cwa_threshold = 1.0
        else:
            pipeline.cwa_threshold = 0.60
            
        preds_all, golds_all = [], []
        for item in data:
            pred = run_pipeline_verification(item["text"], item.get("triples", []), pipeline, "rmit")
            preds_all.append(pred)
            golds_all.append(item["gold_label"])
            
        preds_sparse, golds_sparse = [], []
        for item in sparse_items:
            pred = run_pipeline_verification(item["text"], item.get("triples", []), pipeline, "rmit")
            preds_sparse.append(pred)
            golds_sparse.append(item["gold_label"])

        stratified_results[mode] = {
            "overall": compute_single_pass_metrics(preds_all, golds_all),
            "sparse_relations": compute_single_pass_metrics(preds_sparse, golds_sparse)
        }
        
    return stratified_results

def run_theta_sweep_rmit(data, pipeline):
    sweep = []
    for theta in np.arange(0.0, 1.05, 0.1):
        pipeline.abstention_threshold = float(theta)
        preds, golds = [], []
        for item in data:
            pred = run_pipeline_verification(item["text"], item.get("triples", []), pipeline, "rmit")
            preds.append(pred)
            golds.append(item["gold_label"])
        metrics = compute_single_pass_metrics(preds, golds)
        coverage = min(1.0, sum(1 for p in preds if p in ["Supported", "Contradicted"]) / len(preds))
        sweep.append({
            "theta": round(float(theta), 2),
            "coverage": round(float(coverage), 4),
            "accuracy": round(metrics["accuracy"], 4),
            "macro_f1": round(metrics["macro_f1"], 4),
            "fcr_fraction": metrics["fcr_fraction"],
            "fcr_pct": round(metrics["fcr_pct"], 4),
            "contradiction_recall": round(metrics["contradiction_recall"], 4)
        })
    return sweep

def main():
    print("=== EXECUTING SINGLE PASS REVISION METRIC GENERATOR ===")

    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    rmit_data.append({"text": item.get("raw_claim", item["text"]), "gold_label": g_lbl, "triples": item.get("triples", [])})

    cat2_adapter = Catalog2Adapter()
    cat2_data = cat2_adapter.load_data()[:200]

    factkg_adapter = FactKGAdapter()
    factkg_data = factkg_adapter.load_data()[:500]

    codex_tri_data = []
    if os.path.exists("data/codex_s_tri.jsonl"):
        with open("data/codex_s_tri.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    codex_tri_data.append(json.loads(line))

    metaqa_tri_data = []
    if os.path.exists("data/metaqa_tri.jsonl"):
        with open("data/metaqa_tri.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    metaqa_tri_data.append(json.loads(line))

    pipeline_rmit = VerificationPipeline(kg_path="data/rmit_graph.json")
    pipeline_cat2 = VerificationPipeline(kg_path="data/catalog2_graph.json")
    pipeline_factkg = VerificationPipeline()
    pipeline_codex = VerificationPipeline(kg_path="data/codex_graph.json")
    pipeline_metaqa = VerificationPipeline(kg_path="data/metaqa_graph.json")

    headline_results = {}

    datasets_pipe = [
        ("RMIT", rmit_data, pipeline_rmit, "rmit"),
        ("Catalog2", cat2_data, pipeline_cat2, "catalog2"),
        ("FactKG", factkg_data, pipeline_factkg, "factkg"),
        ("CoDEx-S-Tri", codex_tri_data, pipeline_codex, "codex"),
        ("MetaQA-Tri", metaqa_tri_data, pipeline_metaqa, "metaqa")
    ]

    for ds_name, data, pipe, mode in datasets_pipe:
        if not data:
            continue
        preds, golds = [], []
        for item in data:
            pred = run_pipeline_verification(item["text"], item.get("triples", []), pipe, mode)
            if mode == "factkg":
                if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                    pred = "Contradicted"
                elif pred != "Supported":
                    pred = "Contradicted"
            elif mode in ["codex", "metaqa"]:
                if pred == "Out-of-scope":
                    pred = "Not-in-KG"
            preds.append(pred)
            golds.append(item["gold_label"])

        headline_results[ds_name] = compute_single_pass_metrics(preds, golds)

    e2_stratified = run_e2_stratified_rmit(rmit_data, pipeline_rmit)
    theta_sweep = run_theta_sweep_rmit(rmit_data, pipeline_rmit)

    consolidated = {
        "headline_l1": headline_results,
        "e2_stratified_rmit": e2_stratified,
        "theta_sweep_rmit": theta_sweep
    }

    os.makedirs("output/experiments", exist_ok=True)
    with open("output/experiments/single_pass_revised_metrics.json", "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2)

    print("SUCCESS: Saved single pass metrics to output/experiments/single_pass_revised_metrics.json")
    print(f"RMIT Single Pass Accuracy: {headline_results['RMIT']['accuracy']:.4f}")
    print(f"RMIT Single Pass Macro-F1: {headline_results['RMIT']['macro_f1']:.4f}")

if __name__ == "__main__":
    main()
