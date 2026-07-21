import os
import sys
import json
import random
import logging
import numpy as np

# Ensure project root is in path
sys.path.append(os.getcwd())

from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from llm_client import get_llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("confidence_comparison")

def get_verbalized_confidence(claim, triples, llm_client):
    system_prompt = (
        "You are an expert fact-verification assistant. You will be given a claim and a list of context triples (Knowledge Graph).\n"
        "Verify the claim and output: \n"
        "1. A tri-state verdict ('Supported', 'Contradicted', or 'Not-in-KG')\n"
        "2. A verbalized confidence score representing your subjective certainty in this verdict (float from 0.0 to 1.0).\n\n"
        "Output a raw JSON object only containing the keys 'verdict' and 'confidence'."
    )
    context_str = "\n".join(f"({t[0]}, {t[1]}, {t[2]})" for t in triples) if triples else "No context triples."
    prompt = f"Context:\n{context_str}\n\nClaim: \"{claim}\"\n\nJSON Output:"
    try:
        res = llm_client.generate_json(prompt, system_prompt=system_prompt, temperature=0.3)
        return float(res.get("confidence", 0.5))
    except Exception:
        return 0.5

def get_ensemble_confidence(claim, triples, llm_client):
    # Run verifier 3 times at T=0.5 and compute majority vote and consensus rate
    system_prompt = (
        "You are an expert fact-verification assistant. Verify the claim against the context triples.\n"
        "Output a raw JSON object containing the key 'verdict' (Supported, Contradicted, or Not-in-KG)."
    )
    context_str = "\n".join(f"({t[0]}, {t[1]}, {t[2]})" for t in triples) if triples else "No context triples."
    prompt = f"Context:\n{context_str}\n\nClaim: \"{claim}\"\n\nJSON Output:"
    
    votes = []
    for _ in range(3):
        try:
            res = llm_client.generate_json(prompt, system_prompt=system_prompt, temperature=0.5)
            v = res.get("verdict", "Not-in-KG").strip()
            if "support" in v.lower():
                votes.append("Supported")
            elif "contradict" in v.lower() or "refut" in v.lower():
                votes.append("Contradicted")
            else:
                votes.append("Not-in-KG")
        except Exception:
            votes.append("Not-in-KG")
            
    if not votes:
        return 0.33
        
    # Count occurrences
    counts = {}
    for v in votes:
        counts[v] = counts.get(v, 0) + 1
    majority_count = max(counts.values())
    consensus_rate = majority_count / len(votes)
    return consensus_rate

def get_nli_confidence(claim, triples, llm_client):
    # NLI verifier prompt
    system_prompt = (
        "You are a Natural Language Inference (NLI) model. Determine the entailment relationship between the premises (context triples) and the hypothesis (claim).\n"
        "Output a raw JSON object containing the key 'entailment_probability' (float from 0.0 to 1.0 representing how strongly the premise implies the hypothesis)."
    )
    context_str = "\n".join(f"({t[0]}, {t[1]}, {t[2]})" for t in triples) if triples else "No context triples."
    prompt = f"Premise (Triples):\n{context_str}\n\nHypothesis (Claim): \"{claim}\"\n\nJSON Output:"
    try:
        res = llm_client.generate_json(prompt, system_prompt=system_prompt, temperature=0.2)
        return float(res.get("entailment_probability", 0.5))
    except Exception:
        return 0.5

def calculate_ece(confidences, gold_matches, num_bins=5):
    # ECE formula calculation
    bin_boundaries = np.linspace(0.0, 1.0, num_bins + 1)
    ece = 0.0
    n = len(confidences)
    if n == 0:
        return 0.0
        
    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        # Get elements in bin
        in_bin = [idx for idx, c in enumerate(confidences) if bin_lower <= c < bin_upper or (i == num_bins - 1 and c == bin_upper)]
        prop_in_bin = len(in_bin) / n
        
        if len(in_bin) > 0:
            bin_acc = sum(gold_matches[idx] for idx in in_bin) / len(in_bin)
            bin_conf = sum(confidences[idx] for idx in in_bin) / len(in_bin)
            ece += prop_in_bin * abs(bin_acc - bin_conf)
            
    return ece

def main():
    logger.info("Loading FactKG dataset...")
    adapter = FactKGAdapter()
    data = adapter.load_data()
    
    # Evaluate on a representative sample of 15 items for speed and cost
    data = data[:15]
    
    pipeline = VerificationPipeline()
    llm_client = get_llm_client()
    
    methods = ["composed", "verbalized", "ensemble", "nli"]
    results = {m: {"confidences": [], "gold_matches": []} for m in methods}
    
    logger.info(f"Evaluating confidence baselines on {len(data)} items...")
    
    for idx, item in enumerate(data):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])
        
        logger.info(f"[{idx+1}/{len(data)}] Claim: \"{claim}\" (Gold: {gold})")
        
        # 1. Composed confidence (Ours)
        pipeline.store.courses = {}
        for s, r, o in triples:
            s_norm, r_norm, o_norm = str(s).strip(), str(r).strip(), str(o).strip()
            if s_norm not in pipeline.store.courses:
                pipeline.store.courses[s_norm] = {"course_id": s_norm, "title": s_norm, "credits": 12, "school": "Science", "coordinator": "Unknown", "coordinator_email": "Unknown", "prerequisites": []}
            pipeline.store.courses[s_norm][r_norm] = o_norm
        pipeline.build_entity_index()
        
        relations = list(set(t[1] for t in triples))
        relations_str = "\n".join(f"- {r}: relationship in context." for r in relations) if relations else ""
        factkg_prompt = (
            "You are a factual claim extraction assistant. Decompose the text into atomic, schema-guided claims. "
            f"Each claim must map to one of these valid relation classes:\n{relations_str}\n\n"
            "Return a JSON object with a single key 'claims' containing a list of claims. "
            "Each claim must have: 'subject', 'relation', 'object', 'claim_type'."
        )
        
        res = pipeline.verify_statement(claim, custom_system_prompt=factkg_prompt)
        pred = res["overall_verdict"]
        
        # Normalize prediction label space based on FactKG binary rules
        norm_pred = pred
        if norm_pred in ["Not-in-KG", "Out-of-scope"]:
            norm_pred = "Abstained"
        elif norm_pred != "Supported":
            norm_pred = "Contradicted"
            
        gold_match = 1 if norm_pred == gold else 0
        
        # Record composed confidence
        avg_conf = np.mean([c.get("confidence", 0.5) for c in res["claims"]]) if res["claims"] else 0.5
        results["composed"]["confidences"].append(avg_conf)
        results["composed"]["gold_matches"].append(gold_match)
        
        # 2. Verbalized confidence
        verbalized = get_verbalized_confidence(claim, triples, llm_client)
        results["verbalized"]["confidences"].append(verbalized)
        results["verbalized"]["gold_matches"].append(gold_match)
        
        # 3. Ensemble disagreement
        ensemble = get_ensemble_confidence(claim, triples, llm_client)
        results["ensemble"]["confidences"].append(ensemble)
        results["ensemble"]["gold_matches"].append(gold_match)
        
        # 4. NLI verifier
        nli = get_nli_confidence(claim, triples, llm_client)
        results["nli"]["confidences"].append(nli)
        results["nli"]["gold_matches"].append(gold_match)
        
    # Calculate ECE for each method
    eces = {}
    for m in methods:
        eces[m] = calculate_ece(results[m]["confidences"], results[m]["gold_matches"])
        
    # Generate risk-coverage curves data
    # Coverage vs. Selective Accuracy at thresholds from 0.0 to 0.9
    risk_coverage = {m: [] for m in methods}
    for m in methods:
        confs = np.array(results[m]["confidences"])
        matches = np.array(results[m]["gold_matches"])
        
        for t in np.linspace(0.0, 0.9, 10):
            covered_indices = np.where(confs >= t)[0]
            coverage = len(covered_indices) / len(confs)
            
            if len(covered_indices) > 0:
                sel_acc = np.mean(matches[covered_indices])
            else:
                sel_acc = 1.0
                
            risk_coverage[m].append({
                "threshold": float(t),
                "coverage": float(coverage),
                "selective_accuracy": float(sel_acc)
            })
            
    print("\n" + "="*60)
    print("CONFIDENCE CALIBRATION COMPARISON REPORT (ECE)")
    print("="*60)
    for m in methods:
        print(f"{m.capitalize():<12} | ECE: {eces[m]:.4f}")
    print("="*60 + "\n")
    
    # Save results to output
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "confidence_comparison_results.json")
    with open(report_path, "w") as f:
        json.dump({
            "eces": eces,
            "risk_coverage": risk_coverage
        }, f, indent=2)
    logger.info(f"Saved comparison report to {report_path}")

if __name__ == "__main__":
    main()
