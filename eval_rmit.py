import argparse
import os
import json
import logging
import random
from verification_pipeline import VerificationPipeline
from eval_harness import compute_metrics, print_markdown_table
from llm_client import get_llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_rmit")

def main():
    parser = argparse.ArgumentParser(description="RMIT Handbook Claim-Verification Evaluation")
    parser.add_argument("--test_set", default="data/rmit_test_set.jsonl")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--provider", choices=["azure", "local"], default=None)
    parser.add_argument("--model_name", default=None)
    parser.add_argument("--max_workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output_file", default="output/rmit_evaluation_run.json")
    args = parser.parse_args()

    random.seed(args.seed)
    test_set_path = args.test_set
    if not os.path.exists(test_set_path):
        logger.error(f"Test set not found at {test_set_path}. Run generate_dataset.py first.")
        return 2
        
    logger.info("Initializing Verification Pipeline...")
    llm_client = get_llm_client(provider=args.provider, model=args.model_name)
    pipeline = VerificationPipeline(llm_client=llm_client)
    
    logger.info(f"Loading evaluation dataset: {test_set_path}")
    data = []
    with open(test_set_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    data = data[:args.limit]
                
    logger.info(f"Loaded {len(data)} test items.")
    
    predictions = [None] * len(data)
    gold_labels = [None] * len(data)
    results_detail = [None] * len(data)
    
    def evaluate_rmit_item(idx, item):
        text = item["text"]
        gold = item["gold_label"]
        reasoning = item["reasoning_type"]
        raw_claim = item.get("raw_claim", text)
        
        res = pipeline.verify_statement(raw_claim)
        pred = res["overall_verdict"]
        
        return idx, pred, gold, {
            "id": item["id"],
            "text": text,
            "raw_claim": raw_claim,
            "gold": gold,
            "pred": pred,
            "reasoning_type": reasoning,
            "claims_detail": res["claims"]
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(evaluate_rmit_item, idx, item): idx for idx, item in enumerate(data)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                i, pred, gold, detail = future.result()
                predictions[i] = pred
                gold_labels[i] = gold
                results_detail[i] = detail
            except Exception as e:
                logger.error(f"Error evaluating RMIT item {idx}: {e}")
                predictions[idx] = "Contradicted"
                gold_labels[idx] = data[idx]["gold_label"]
                results_detail[idx] = {
                    "id": data[idx]["id"],
                    "text": data[idx]["text"],
                    "raw_claim": data[idx].get("raw_claim", data[idx]["text"]),
                    "gold": data[idx]["gold_label"],
                    "pred": "Error",
                    "reasoning_type": data[idx]["reasoning_type"],
                    "claims_detail": []
                }
        
    # Calculate metrics
    accuracy, class_metrics, ci_lower, ci_upper = compute_metrics(predictions, gold_labels)
    
    print("\n" + "="*60)
    print("RMIT HANDBOOK KNOWLEDGE GRAPH VERIFICATION REPORT")
    print("="*60)
    print(f"Total Evaluated: {len(data)}")
    print(f"E2E System Accuracy: {accuracy:.2%} (95% CI: [{ci_lower:.2%}, {ci_upper:.2%}])\n")
    
    print("Metrics by Verdict Class:")
    headers = ["Class", "Precision", "Recall", "F1-Score", "Support"]
    print_markdown_table(headers, class_metrics)
    
    print("\nAccuracy by Reasoning Type:")
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
    
    print("\nIncorrect Predictions (Sample Debug Output):")
    err_count = 0
    for res in results_detail:
        if res["pred"] != res["gold"]:
            print(f"- Query: \"{res['text']}\"")
            print(f"  Raw: \"{res['raw_claim']}\"")
            print(f"  Gold: {res['gold']} | Predicted: {res['pred']} | Reasoning: {res['reasoning_type']}")
            print("  Decomposed Claims:")
            for cl in res["claims_detail"]:
                print(f"    * Claim: \"{cl['claim_text']}\" -> Verdict: {cl['verdict']} (Reason: {cl['reason']})")
            err_count += 1
            if err_count >= 5:
                break
    if err_count == 0:
        print("None! Perfect validation accuracy achieved.")
    print("="*60 + "\n")

    report_json_path = args.output_file
    output_dir = os.path.dirname(report_json_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    report = {
        "dataset": "rmit",
        "method": "pipeline",
        "model_name": llm_client.model,
        "provider": llm_client.provider,
        "seed": args.seed,
        "max_workers": args.max_workers,
        "total_evaluated": len(data),
        "accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "class_metrics": class_metrics,
        "results_detail": results_detail,
    }
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved detailed run logs to {report_json_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
