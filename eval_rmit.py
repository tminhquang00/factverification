import argparse
import os
import json
import logging
import random
import time
from verification_pipeline import VerificationPipeline
from eval_harness import (
    compute_metrics,
    print_markdown_table,
    run_closed_book_verification,
    run_context_verification,
)
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
    parser.add_argument("--withhold_unresolved_claims", action="store_true",
                        help="Ablation: withhold claims whose subject could not be linked from the "
                             "verdict vote. Off by default — measured at +0.8 pts on CoDEx (inside "
                             "the noise floor) against -2.67 pts on RMIT.")
    parser.add_argument("--method", type=str, default="pipeline",
                        choices=["closed_book_llm", "context_llm", "pipeline"],
                        help="Verification method. Baseline arms mirror eval_harness.py so the domain "
                             "set is compared against the same baselines as the public benchmarks: "
                             "'closed_book_llm' prompts the LLM with no graph, 'context_llm' supplies "
                             "the row's gold triples (an oracle-retrieval upper bound, not retrieval).")
    parser.add_argument("--verify_field", type=str, default="raw_claim",
                        choices=["raw_claim", "text"],
                        help="Which field is submitted for verification. 'raw_claim' is the template "
                             "interpolated from the graph's own field names — accuracy on it is inflated "
                             "by construction (the circularity gap). 'text' is the natural-language "
                             "question. Run both on identical rows to measure the gap.")
    parser.add_argument("--routing_mode", type=str, default=None,
                        choices=["declared", "occupancy", "dynamic", "fixed_cwa", "fixed_owa"],
                        help="World-assumption dispatch (E2 ablation arm). See eval_harness.py.")
    parser.add_argument("--cwa_threshold", type=float, default=None,
                        help="Occupancy at or above which a relation is treated as closed-world under "
                             "--routing_mode dynamic. Swept 0.50-0.95 in the E2 ablation.")
    args = parser.parse_args()

    random.seed(args.seed)
    test_set_path = args.test_set
    if not os.path.exists(test_set_path):
        logger.error(f"Test set not found at {test_set_path}. Run generate_dataset.py first.")
        return 2
        
    llm_client = get_llm_client(provider=args.provider, model=args.model_name)

    pipeline = None
    if args.method == "pipeline":
        logger.info("Initializing Verification Pipeline...")
        pipeline_kwargs = dict(
            llm_client=llm_client,
            withhold_unresolved_claims=args.withhold_unresolved_claims,
        )
        if args.routing_mode is not None:
            pipeline_kwargs["routing_mode"] = args.routing_mode
        if args.cwa_threshold is not None:
            pipeline_kwargs["cwa_threshold"] = args.cwa_threshold
        pipeline = VerificationPipeline(**pipeline_kwargs)
    else:
        logger.info(f"Running baseline arm '{args.method}' — the verification pipeline is not used.")
        if args.routing_mode is not None or args.cwa_threshold is not None:
            logger.warning("--routing_mode/--cwa_threshold have no effect outside --method pipeline.")

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
        # The verified string is a switch, not a hard-coded field: raw_claim is interpolated from
        # the graph's own field names, so accuracy on it is circular by construction.
        verified_input = raw_claim if args.verify_field == "raw_claim" else text

        row_started = time.perf_counter()
        with llm_client.usage.scope() as row_usage:
            if args.method == "closed_book_llm":
                pred = run_closed_book_verification(verified_input, llm_client)
                claims_detail = []
            elif args.method == "context_llm":
                pred = run_context_verification(verified_input, item.get("triples", []), llm_client)
                claims_detail = []
            else:
                res = pipeline.verify_statement(verified_input)
                pred = res["overall_verdict"]
                claims_detail = res["claims"]
        row_usage = dict(row_usage, wall_clock_s=time.perf_counter() - row_started)

        return idx, pred, gold, {
            "id": item["id"],
            "text": text,
            "raw_claim": raw_claim,
            "verified_input": verified_input,
            "gold": gold,
            "pred": pred,
            "raw_pred": pred,
            "reasoning_type": reasoning,
            "usage": row_usage,
            "claims_detail": claims_detail
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
                # A crash is not a prediction; leave the row unscored rather than defaulting it.
                # This applies to the baseline arms too — they re-raise instead of returning a label.
                logger.error(f"Error evaluating RMIT item {idx}: {e}")
                predictions[idx] = None
                gold_labels[idx] = data[idx]["gold_label"]
                raw_claim_err = data[idx].get("raw_claim", data[idx]["text"])
                results_detail[idx] = {
                    "id": data[idx]["id"],
                    "text": data[idx]["text"],
                    "raw_claim": raw_claim_err,
                    "verified_input": raw_claim_err if args.verify_field == "raw_claim" else data[idx]["text"],
                    "gold": data[idx]["gold_label"],
                    "pred": None,
                    "raw_pred": "Error",
                    "error": str(e),
                    "reasoning_type": data[idx]["reasoning_type"],
                    "claims_detail": []
                }

    # Calculate metrics (unscored crash rows are excluded from the denominator)
    accuracy, class_metrics, ci_lower, ci_upper, n_scored = compute_metrics(predictions, gold_labels)
    run_usage = llm_client.usage.snapshot()
    run_usage["per_row"] = {
        "n_rows": len(data),
        "tokens_per_row": (run_usage["total_tokens"] / len(data)) if data else None,
        "calls_per_row": (run_usage["n_calls"] / len(data)) if data else None,
    }
    print("\n" + "="*60)
    print("RMIT HANDBOOK KNOWLEDGE GRAPH VERIFICATION REPORT")
    print("="*60)
    print(f"Method: {args.method}   Verified field: {args.verify_field}"
          + (f"   Routing: {args.routing_mode or 'pipeline default'}"
             f" @ tau_cwa={args.cwa_threshold if args.cwa_threshold is not None else 'default'}"
             if args.method == "pipeline" else ""))
    if args.verify_field == "raw_claim":
        print("NOTE: raw_claim is interpolated from the graph's own field names; accuracy on it is")
        print("      inflated by construction. Report it only alongside --verify_field text.")
    print(f"Total Items: {len(data)}")
    print(f"Scored: {n_scored}   Unscored (call raised): {len(data) - n_scored}")
    print(f"E2E System Accuracy (over scored rows): {accuracy:.2%} (95% CI: [{ci_lower:.2%}, {ci_upper:.2%}])")
    _lat = run_usage["latency_s"]
    print(f"Cost: {run_usage['n_calls']} LLM calls, {run_usage['total_tokens']} tokens "
          f"({run_usage['per_row']['calls_per_row']:.2f} calls/row, "
          f"{run_usage['per_row']['tokens_per_row']:.1f} tokens/row)"
          + ("" if run_usage["tokens_complete"]
             else f" — WARNING: {run_usage['n_calls_without_usage']} calls returned no usage block, "
                  "token totals are a lower bound"))
    if _lat["mean"] is not None:
        print(f"Latency per call: mean {_lat['mean']:.2f}s, p50 {_lat['p50']:.2f}s, "
              f"p95 {_lat['p95']:.2f}s, max {_lat['max']:.2f}s\n")
    else:
        print("")
    
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
            print(f"  Verified ({args.verify_field}): \"{res.get('verified_input', res['raw_claim'])}\"")
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
        "method": args.method,
        "verify_field": args.verify_field,
        "routing_mode": pipeline.routing_mode if pipeline is not None else args.routing_mode,
        "completeness_path": (pipeline.store.completeness_path if pipeline is not None else None),
        "cwa_threshold": args.cwa_threshold,
        "model_name": llm_client.model,
        "provider": llm_client.provider,
        "seed": args.seed,
        "max_workers": args.max_workers,
        "total_evaluated": len(data),
        "n_scored": n_scored,
        "n_unscored_errors": len(data) - n_scored,
        "accuracy": accuracy,
        "ci_95": [ci_lower, ci_upper],
        "class_metrics": class_metrics,
        "usage": run_usage,
        "results_detail": results_detail,
    }
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved detailed run logs to {report_json_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
