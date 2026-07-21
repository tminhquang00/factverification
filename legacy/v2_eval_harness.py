import os
import argparse
import logging
import json
from adapters.factkg_adapter import FactKGAdapter
from adapters.fever_adapter import FEVERAdapter
from llm_client import get_llm_client
from verification_pipeline import VerificationPipeline

# Simple console logger setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eval_harness")

def print_markdown_table(headers, rows):
    """Prints a beautiful markdown table to the console."""
    # Find max length of each column
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))
            
    header_line = "| " + " | ".join(f"{str(h).ljust(w)}" for h, w in zip(headers, col_widths)) + " |"
    separator = "| " + " | ".join("-" * w for w in col_widths) + " |"
    print(header_line)
    print(separator)
    for row in rows:
        row_line = "| " + " | ".join(f"{str(val).ljust(w)}" for val, w in zip(row, col_widths)) + " |"
        print(row_line)

def compute_metrics(predictions, gold_labels):
    classes = ["Supported", "Contradicted", "Not-in-KG"]
    metrics = {c: {"tp": 0, "fp": 0, "fn": 0} for c in classes}
    correct = 0
    total = len(predictions)
    
    for pred, gold in zip(predictions, gold_labels):
        if pred == gold:
            correct += 1
            if pred in metrics:
                metrics[pred]["tp"] += 1
        else:
            if pred in metrics:
                metrics[pred]["fp"] += 1
            if gold in metrics:
                metrics[gold]["fn"] += 1
                
    accuracy = correct / total if total > 0 else 0
    
    rows = []
    for c in classes:
        tp = metrics[c]["tp"]
        fp = metrics[c]["fp"]
        fn = metrics[c]["fn"]
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        # Calculate support
        support = tp + fn
        rows.append([c, f"{precision:.2%}", f"{recall:.2%}", f"{f1:.2%}", support])
        
    return accuracy, rows

def run_closed_book_verification(claim: str, llm_client):
    system_prompt = (
        "You are an expert fact-verification assistant. Your task is to analyze the claim and classify it into one of three classes:\n"
        "1. Supported: The claim is true and factual.\n"
        "2. Contradicted: The claim is false, inaccurate, or contains a hallucinated detail.\n"
        "3. Not-in-KG: There is not enough information to verify the claim, or it contains unknown entities.\n\n"
        "Respond with a JSON object containing exactly the keys 'verdict', 'reason', and 'evidence'. "
        "The 'verdict' key must be exactly one of: 'Supported', 'Contradicted', 'Not-in-KG'."
    )
    prompt = f"Verify the following claim:\nClaim: \"{claim}\"\n\nJSON Output:"
    
    try:
        res = llm_client.generate_json(prompt, system_prompt=system_prompt)
        verdict = res.get("verdict", "Not-in-KG").strip()
        # Clean verdict matching
        if "support" in verdict.lower():
            return "Supported"
        elif "contradict" in verdict.lower() or "refut" in verdict.lower():
            return "Contradicted"
        else:
            return "Not-in-KG"
    except Exception as e:
        logger.error(f"Error calling LLM for verification: {e}")
        return "Not-in-KG"

def run_context_verification(claim: str, triples: list, llm_client):
    system_prompt = (
        "You are an expert fact-verification assistant. You will be given a claim and a list of factual triples representing the context (Knowledge Graph).\n"
        "Determine if the claim is:\n"
        "1. Supported: The claim is supported directly by the triples.\n"
        "2. Contradicted: The claim is directly contradicted by the facts in the triples (e.g., mismatching values or entities).\n"
        "3. Not-in-KG: The triples do not contain enough information to verify this claim.\n\n"
        "Respond with a JSON object containing exactly the keys 'verdict', 'reason', and 'evidence'. "
        "The 'verdict' key must be exactly one of: 'Supported', 'Contradicted', 'Not-in-KG'."
    )
    context_str = "\n".join(f"({t[0]}, {t[1]}, {t[2]})" for t in triples) if triples else "No context triples available."
    prompt = f"Context Triples:\n{context_str}\n\nClaim to Verify: \"{claim}\"\n\nJSON Output:"
    
    try:
        res = llm_client.generate_json(prompt, system_prompt=system_prompt)
        verdict = res.get("verdict", "Not-in-KG").strip()
        if "support" in verdict.lower():
            return "Supported"
        elif "contradict" in verdict.lower() or "refut" in verdict.lower():
            return "Contradicted"
        else:
            return "Not-in-KG"
    except Exception as e:
        logger.error(f"Error calling LLM: {e}")
        return "Not-in-KG"

def run_pipeline_verification(claim: str, triples: list, pipeline, dataset: str):
    # Populate pipeline's KG store temporarily with the context triples
    pipeline.store.courses = {}
    
    for s, r, o in triples:
        s_norm = str(s).strip()
        r_norm = str(r).strip()
        o_norm = str(o).strip()
        
        if s_norm not in pipeline.store.courses:
            pipeline.store.courses[s_norm] = {
                "course_id": s_norm,
                "title": s_norm,
                "credits": 12,
                "school": "Science",
                "coordinator": "Unknown",
                "coordinator_email": "Unknown",
                "prerequisites": [],
                "description": ""
            }
            
        pipeline.store.courses[s_norm][r_norm] = o_norm

    # Rebuild entity index
    pipeline.build_entity_index()
    
    if dataset == "factkg":
        # Extract unique relations present in the context triples for this specific claim
        relations = list(set(t[1] for t in triples))
        if not relations:
            relations = ["capital", "birthPlace", "founded", "father", "mother", "office", "type"]
            
        relations_str = "\n".join(f"- {r}: relationship in context triples." for r in relations)
        
        factkg_prompt = (
            "You are a factual claim extraction assistant. Decompose the text into atomic, schema-guided claims. "
            f"Each claim must map to one of these valid relation classes:\n{relations_str}\n\n"
            "Return a JSON object with a single key 'claims' containing a list of claims. "
            "Each claim must have: 'subject', 'relation', 'object', 'claim_type'. "
            "Set 'claim_type' to the relation name if it fits. If the claim does not fit any of the relations, set 'claim_type' to 'unclassified'."
        )
        res = pipeline.verify_statement(claim, custom_system_prompt=factkg_prompt)
    else:
        res = pipeline.verify_statement(claim)
        
    return res["overall_verdict"]

def main():
    parser = argparse.ArgumentParser(description="Public Fact Verification Baseline Evaluation Harness")
    parser.add_argument("--dataset", type=str, default="factkg", choices=["factkg", "fever"], help="Dataset to run on")
    parser.add_argument("--method", type=str, default="closed_book_llm", choices=["closed_book_llm", "context_llm", "pipeline"], help="Verification method")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of items to evaluate")
    args = parser.parse_args()

    # Get the LLM Client
    llm_client = get_llm_client()
    
    # Initialize adapter
    if args.dataset == "factkg":
        adapter = FactKGAdapter()
    else:
        adapter = FEVERAdapter()
        
    data = adapter.load_data()
    data = adapter.load_data()
    data = data[:args.limit]
    
    pipeline = None
    if args.method == "pipeline":
        pipeline = VerificationPipeline()
        
    logger.info(f"Running evaluation on {len(data)} items from {args.dataset} using {args.method}...")
    
    predictions = []
    gold_labels = []
    results_detail = []
    
    for idx, item in enumerate(data):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])
        
        logger.info(f"[{idx+1}/{len(data)}] Claim: \"{claim}\" (Gold: {gold})")
        
        if args.method == "closed_book_llm":
            pred = run_closed_book_verification(claim, llm_client)
        elif args.method == "pipeline":
            pred = run_pipeline_verification(claim, triples, pipeline, args.dataset)
        else:
            pred = run_context_verification(claim, triples, llm_client)
            
        logger.info(f"  Prediction: {pred}")
        predictions.append(pred)
        gold_labels.append(gold)
        results_detail.append({
            "id": item["id"],
            "claim": claim,
            "gold": gold,
            "pred": pred,
            "reasoning_type": item.get("reasoning_type", "N/A")
        })
        
    # Compute metrics
    accuracy, class_metrics = compute_metrics(predictions, gold_labels)
    
    # Print results
    print("\n" + "="*60)
    print(f"EVALUATION REPORT: {args.dataset.upper()} - {args.method.upper()}")
    print("="*60)
    print(f"Total Evaluated: {len(data)}")
    print(f"Accuracy: {accuracy:.2%}\n")
    
    headers = ["Class", "Precision", "Recall", "F1-Score", "Support"]
    print_markdown_table(headers, class_metrics)
    
    # Reasoning type breakdown (if FactKG)
    if args.dataset == "factkg":
        print("\nReasoning Type Breakdown:")
        reasoning_types = set(item["reasoning_type"] for item in results_detail)
        r_rows = []
        for r_type in sorted(reasoning_types):
            r_items = [item for item in results_detail if item["reasoning_type"] == r_type]
            r_preds = [item["pred"] for item in r_items]
            r_golds = [item["gold"] for item in r_items]
            r_correct = sum(1 for p, g in zip(r_preds, r_golds) if p == g)
            r_acc = r_correct / len(r_items) if r_items else 0
            r_rows.append([r_type, len(r_items), f"{r_acc:.2%}"])
        print_markdown_table(["Reasoning Type", "Count", "Accuracy"], r_rows)
        
    # Show error instances
    print("\nIncorrect Predictions (Sample):")
    err_count = 0
    for res in results_detail:
        if res["pred"] != res["gold"]:
            print(f"- Claim: \"{res['claim']}\"\n  Gold: {res['gold']} | Pred: {res['pred']} | Reasoning: {res['reasoning_type']}")
            err_count += 1
            if err_count >= 5:
                break
    if err_count == 0:
        print("None! All predictions were correct.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
