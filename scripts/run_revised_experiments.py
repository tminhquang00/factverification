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
from eval_harness import compute_metrics, run_pipeline_verification
from sklearn.model_selection import KFold
from sklearn.linear_model import LogisticRegression

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("revised_experiments")

def compute_macro_f1(predictions, gold_labels):
    classes = sorted(list(set(gold_labels + predictions)))
    f1s = []
    for c in classes:
        tp = sum(1 for p, g in zip(predictions, gold_labels) if p == c and g == c)
        fp = sum(1 for p, g in zip(predictions, gold_labels) if p == c and g != c)
        fn = sum(1 for p, g in zip(predictions, gold_labels) if p != c and g == c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return float(np.mean(f1s)) if f1s else 0.0

def compute_fcr(predictions, gold_labels):
    # False Contradiction Rate: P(gold in {Supported, Not-in-KG} | pred == Contradicted)
    contradicted_indices = [i for i, p in enumerate(predictions) if p == "Contradicted"]
    if not contradicted_indices:
        return 0.0
    false_contradictions = sum(1 for i in contradicted_indices if gold_labels[i] in ["Supported", "Not-in-KG"])
    return float(false_contradictions / len(contradicted_indices))

def run_e2_routing_ablation(dataset_name, data, pipeline):
    logger.info(f"Running E2 World-Assumption Routing Ablation on {dataset_name} ({len(data)} items)...")
    results = {}
    
    for mode in ["dynamic", "fixed_cwa", "fixed_owa"]:
        preds = []
        golds = []
        for item in data:
            claim = item["text"]
            gold = item["gold_label"]
            triples = item.get("triples", [])
            
            # Temporary override of CWA mode in pipeline
            if mode == "fixed_cwa":
                pipeline.cwa_threshold = 0.0 # Force CWA
            elif mode == "fixed_owa":
                pipeline.cwa_threshold = 1.0 # Force OWA
            else:
                pipeline.cwa_threshold = 0.60
                
            pred = run_pipeline_verification(claim, triples, pipeline, dataset_name)
            if dataset_name == "factkg":
                if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                    pred = "Contradicted"
                elif pred != "Supported":
                    pred = "Contradicted"
            elif dataset_name in ["codex", "metaqa"]:
                if pred == "Out-of-scope":
                    pred = "Not-in-KG"
                    
            preds.append(pred)
            golds.append(gold)
            
        acc, _, ci_low, ci_high = compute_metrics(preds, golds)
        macro_f1 = compute_macro_f1(preds, golds)
        fcr = compute_fcr(preds, golds)
        
        results[mode] = {
            "accuracy": acc,
            "ci_95": [ci_low, ci_high],
            "macro_f1": macro_f1,
            "false_contradiction_rate": fcr
        }
    return results

def run_e5_cross_fitted_meta_confidence(dataset_name, records):
    logger.info(f"Running E5 5-Fold Cross-Fitted Meta-Confidence on {dataset_name} ({len(records)} records)...")
    X = np.array([r["features"] for r in records])
    y = np.array([r["is_match"] for r in records])
    
    if len(X) < 10 or len(set(y)) < 2:
        return {}
        
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    meta_preds = np.zeros(len(y))
    
    for train_idx, val_idx in kf.split(X):
        clf = LogisticRegression(C=1.0, max_iter=500)
        clf.fit(X[train_idx], y[train_idx])
        meta_preds[val_idx] = clf.predict_proba(X[val_idx])[:, 1]
        
    # Feature-group ablations (drop one feature at a time)
    feature_names = ["C(R)", "entity_score", "decomp_agreed", "nli_conf", "is_supp", "is_contra", "is_nik", "hop_count"]
    ablations = {}
    
    for feat_idx, feat_name in enumerate(feature_names):
        X_sub = np.delete(X, feat_idx, axis=1)
        sub_preds = np.zeros(len(y))
        for train_idx, val_idx in kf.split(X_sub):
            clf = LogisticRegression(C=1.0, max_iter=500)
            clf.fit(X_sub[train_idx], y[train_idx])
            sub_preds[val_idx] = clf.predict_proba(X_sub[val_idx])[:, 1]
        ablations[f"without_{feat_name}"] = float(np.mean(sub_preds == y))
        
    acc = float(np.mean((meta_preds >= 0.5) == y))
    return {
        "cross_val_accuracy": acc,
        "feature_group_ablations": ablations
    }

def main():
    os.makedirs("output/experiments", exist_ok=True)
    random.seed(42)
    
    results = {}
    
    # RMIT
    pipeline_rmit = VerificationPipeline(kg_path="data/rmit_graph.json")
    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    rmit_data.append({"text": item.get("raw_claim", item["text"]), "gold_label": g_lbl, "triples": item.get("triples", [])})
                    
    if rmit_data:
        results["e2_routing_rmit"] = run_e2_routing_ablation("rmit", rmit_data, pipeline_rmit)
        
    # FactKG
    factkg_adapter = FactKGAdapter()
    factkg_data = factkg_adapter.load_data()[:150]
    pipeline_factkg = VerificationPipeline()
    results["e2_routing_factkg"] = run_e2_routing_ablation("factkg", factkg_data, pipeline_factkg)
    
    # E5 Cross-fitted Meta-confidence
    from scripts.train_meta_confidence import extract_features_and_run
    llm_client = pipeline_rmit.llm_client
    if rmit_data:
        records_rmit = extract_features_and_run("rmit", rmit_data, pipeline_rmit, llm_client)
        results["e5_meta_confidence_rmit"] = run_e5_cross_fitted_meta_confidence("rmit", records_rmit)
        
    with open("output/experiments/revised_experiments_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    logger.info("Saved Revised Experiments results to output/experiments/revised_experiments_results.json")

if __name__ == "__main__":
    main()
