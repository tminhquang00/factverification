import os
import sys
import json
import logging
import numpy as np

# Add project root to sys.path
sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audit_score_inversion")

def analyze_dataset_inversion(dataset_name, data, pipeline):
    logger.info(f"Auditing score distribution and decile errors for {dataset_name} ({len(data)} items)...")
    
    confidences = []
    matches = []
    verdicts = []
    reasons = []
    entity_scores = []
    claims = []
    gold_labels = []
    
    for idx, item in enumerate(data):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])
        
        # Populate pipeline store if FactKG
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
        
        # Calculate maximum confidence across claims
        claim_confs = [c["confidence"] for c in res["claims"]] if res["claims"] else [0.5]
        conf = max(claim_confs) if claim_confs else 0.5
        
        # Label normalization
        if dataset_name == "factkg":
            if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                pred = "Contradicted"
            elif pred != "Supported":
                pred = "Contradicted"
        elif dataset_name in ["codex", "metaqa"]:
            if pred == "Out-of-scope":
                pred = "Not-in-KG"
                
        is_match = 1 if pred == gold else 0
        
        confidences.append(conf)
        matches.append(is_match)
        verdicts.append(pred)
        reasons.append(res.get("reason", ""))
        entity_scores.append(getattr(pipeline, "last_entity_score", 1.0))
        claims.append(claim)
        gold_labels.append(gold)

    confidences = np.array(confidences)
    matches = np.array(matches)
    
    # 1. Histogram distribution (10 bins)
    bins = np.linspace(0.0, 1.0, 11)
    hist, _ = np.histogram(confidences, bins=bins)
    
    # 2. Count mass ties at confidence >= 0.99
    mass_ties_count = int(np.sum(confidences >= 0.99))
    mass_ties_pct = float(mass_ties_count / len(confidences))
    
    # 3. Top-decile error audit (top 10% most confident items)
    idx_sorted = np.argsort(confidences)[::-1]
    top_k = max(1, int(len(confidences) * 0.10))
    top_decile_indices = idx_sorted[:top_k]
    
    top_decile_correct = int(np.sum(matches[top_decile_indices]))
    top_decile_errors = top_k - top_decile_correct
    top_decile_acc = float(top_decile_correct / top_k)
    top_decile_risk = 1.0 - top_decile_acc
    
    # Categorize top-decile errors
    tie_block_errors = 0
    conf_wrong_contradicted_errors = 0
    other_errors = 0
    
    for i in top_decile_indices:
        if matches[i] == 0: # Error
            c_val = confidences[i]
            v_val = verdicts[i]
            if c_val >= 0.99 and v_val == "Contradicted":
                conf_wrong_contradicted_errors += 1
            elif c_val >= 0.99:
                tie_block_errors += 1
            else:
                other_errors += 1
                
    audit_summary = {
        "dataset": dataset_name,
        "total_items": len(data),
        "overall_accuracy": float(np.mean(matches)),
        "mass_ties_at_1.0_count": mass_ties_count,
        "mass_ties_at_1.0_pct": mass_ties_pct,
        "top_10pct_decile_size": top_k,
        "top_10pct_decile_accuracy": top_decile_acc,
        "top_10pct_decile_risk": top_decile_risk,
        "top_10pct_total_errors": top_decile_errors,
        "error_breakdown": {
            "confidently_wrong_contradicted": conf_wrong_contradicted_errors,
            "tie_block_arbitrary_ordering": tie_block_errors,
            "other_high_confidence_errors": other_errors
        },
        "histogram_bins": [f"{bins[i]:.1f}-{bins[i+1]:.1f}" for i in range(10)],
        "histogram_counts": hist.tolist()
    }
    return audit_summary

def main():
    os.makedirs("output", exist_ok=True)
    
    # Load RMIT data
    pipeline_rmit = VerificationPipeline(kg_path="data/rmit_graph.json")
    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    rmit_data.append({"text": item.get("raw_claim", item["text"]), "gold_label": g_lbl, "triples": item.get("triples", [])})
                    
    # Load CoDEx data
    pipeline_codex = VerificationPipeline(kg_path="data/codex_graph.json")
    codex_adapter = CoDExAdapter()
    codex_data = codex_adapter.load_data()[:150]
    
    audit_results = {}
    if rmit_data:
        audit_results["rmit"] = analyze_dataset_inversion("rmit", rmit_data, pipeline_rmit)
    if codex_data:
        audit_results["codex"] = analyze_dataset_inversion("codex", codex_data, pipeline_codex)
        
    with open("output/inversion_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)
        
    logger.info("Saved inversion audit results to output/inversion_audit_results.json")
    
    # Generate matplotlib histogram figure if available
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        
        for idx, (ds_name, summary) in enumerate(audit_results.items()):
            ax = axes[idx]
            counts = summary["histogram_counts"]
            bin_labels = [f"{i/10:.1f}" for i in range(10)]
            ax.bar(bin_labels, counts, color="skyblue", edgecolor="black")
            ax.set_title(f"Score Histogram: {ds_name.upper()} (Ties @1.0 = {summary['mass_ties_at_1.0_pct']:.1%})")
            ax.set_xlabel("Confidence Score Bin")
            ax.set_ylabel("Frequency")
            
        plt.tight_layout()
        plt.savefig("output/score_distributions.png", dpi=200)
        plt.savefig("docs/score_distributions.png", dpi=200)
        logger.info("Saved score distribution plot to output/score_distributions.png and docs/score_distributions.png")
    except Exception as e:
        logger.warning(f"Could not render histogram plot: {e}")

if __name__ == "__main__":
    main()
