import os
import json
import logging
from verification_pipeline import VerificationPipeline
from eval_harness import compute_metrics, print_markdown_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_rmit")

def main():
    test_set_path = "data/rmit_test_set.jsonl"
    if not os.path.exists(test_set_path):
        logger.error(f"Test set not found at {test_set_path}. Run generate_dataset.py first.")
        return
        
    logger.info("Initializing Verification Pipeline...")
    pipeline = VerificationPipeline()
    
    logger.info(f"Loading evaluation dataset: {test_set_path}")
    data = []
    with open(test_set_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
                
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
    with ThreadPoolExecutor(max_workers=10) as executor:
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

    # Save details to outputs/rmit_evaluation_run.json
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    report_json_path = os.path.join(output_dir, "rmit_evaluation_run.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(results_detail, f, indent=2)
    logger.info(f"Saved detailed run logs to {report_json_path}")

if __name__ == "__main__":
    main()
