import os
import argparse
import logging
import json
import random
import time
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

def bootstrap_confidence_interval(predictions, gold_labels, num_bootstraps=1000, confidence_level=0.95):
    accuracies = []
    n = len(predictions)
    if n == 0:
        return 0.0, 0.0
    for _ in range(num_bootstraps):
        sample_preds = []
        sample_golds = []
        for _ in range(n):
            idx = random.randint(0, n - 1)
            sample_preds.append(predictions[idx])
            sample_golds.append(gold_labels[idx])
        correct = sum(1 for p, g in zip(sample_preds, sample_golds) if p == g)
        accuracies.append(correct / n)
    accuracies.sort()
    lower_idx = int((1 - confidence_level) / 2 * num_bootstraps)
    upper_idx = int((1 + confidence_level) / 2 * num_bootstraps)
    return accuracies[lower_idx], accuracies[upper_idx]

def compute_metrics(predictions, gold_labels):
    """Computes accuracy and per-class metrics over SCORED rows only.

    A prediction of None marks a row the pipeline never produced a verdict for (it raised).
    Such rows are excluded from the denominator rather than being assigned a default label:
    substituting a class label on failure silently converts crashes into accuracy whenever the
    default coincides with the majority class.
    """
    classes = ["Supported", "Contradicted", "Not-in-KG"]
    metrics = {c: {"tp": 0, "fp": 0, "fn": 0} for c in classes}
    correct = 0

    scored = [(p, g) for p, g in zip(predictions, gold_labels) if p is not None]
    total = len(scored)

    for pred, gold in scored:
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
        
    scored_preds = [p for p, _ in scored]
    scored_golds = [g for _, g in scored]
    ci_lower, ci_upper = bootstrap_confidence_interval(scored_preds, scored_golds)
    return accuracy, rows, ci_lower, ci_upper, total

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

    # Exceptions propagate: a failed call is not a prediction. The caller leaves the row unscored,
    # the same rule the pipeline path uses. Returning "Not-in-KG" here would score the baseline
    # under the old pre-D5-fix convention and bias every pipeline-vs-baseline comparison.
    res = llm_client.generate_json(prompt, system_prompt=system_prompt)
    verdict = res.get("verdict", "Not-in-KG").strip()
    # Clean verdict matching
    if "support" in verdict.lower():
        return "Supported"
    elif "contradict" in verdict.lower() or "refut" in verdict.lower():
        return "Contradicted"
    else:
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

    # Exceptions propagate — see run_closed_book_verification. Failures are unscored, not labelled.
    res = llm_client.generate_json(prompt, system_prompt=system_prompt)
    verdict = res.get("verdict", "Not-in-KG").strip()
    if "support" in verdict.lower():
        return "Supported"
    elif "contradict" in verdict.lower() or "refut" in verdict.lower():
        return "Contradicted"
    else:
        return "Not-in-KG"

NUSMODS_DECOMPOSITION_PROMPT = (
    "You are a factual claim extraction assistant working on the NUS module catalogue. "
    "Decompose the text into atomic, schema-guided claims. "
    "Each claim must map to one of these valid relation classes:\n"
    "- hasCreditValue: the module is worth a number of Modular Credits (MCs).\n"
    "- partOfSchool: the module is offered by a NUS faculty or school "
    "(e.g. Computing, Science, Law, NUS Business School). Give the faculty name alone as the "
    "object, without a 'Faculty of' prefix.\n"
    "- requiresPrerequisite: the module requires another module as a prerequisite. If the text "
    "says the module has no prerequisites, emit this relation with the object 'none'.\n\n"
    "Use the module code (e.g. CS2040, LL4367V) as the subject whenever the text gives one. "
    "A parenthesised module title is not a claim; do not emit one for it.\n"
    "If the text says the prerequisite of module A itself requires module C, decompose it into "
    "two claims: A requires B, and B requires C, using the intermediate module B if the text "
    "names it; otherwise emit the single claim that A requires C.\n\n"
    "Return a JSON object with a single key 'claims' containing a list of claims. "
    "Each claim must have: 'subject', 'relation', 'object', 'claim_type'. "
    "Set 'claim_type' to the relation name if it fits. If the claim does not fit any of the "
    "relations, set 'claim_type' to 'unclassified'."
)


def run_pipeline_verification(claim: str, triples: list, pipeline, dataset: str):
    if dataset == "nusmods":
        res = pipeline.verify_statement(claim, custom_system_prompt=NUSMODS_DECOMPOSITION_PROMPT)
        return res["overall_verdict"]

    if dataset in ["codex", "metaqa"]:
        if dataset == "codex":
            codex_prompt = (
                "You are a factual claim extraction assistant. Decompose the statement into atomic, clear factual claims. "
                "Extract the subject entity name, the predicate/relation string, and the object entity/value. "
                "Return a JSON object with a single key 'claims' containing a list of claims. "
                "Each claim must have: 'subject', 'relation', 'object', 'claim_type'. "
                "Set 'claim_type' to the relation name if it fits, or the relation name itself."
            )
            res = pipeline.verify_statement(claim, custom_system_prompt=codex_prompt)
        else:
            metaqa_prompt = (
                "You are a factual claim extraction assistant. Decompose the statement into atomic, clear factual claims. "
                "Extract the subject entity (movie name or actor/director name), relation (e.g. directed_by, starred_actors, has_genre, release_year, writer), and object entity. "
                "For multi-hop statements (e.g. 'X directed a movie that starred Y'), extract the head entity X, relation chain/predicate, and tail entity Y. "
                "Return a JSON object with a single key 'claims' containing a list of claims. "
                "Each claim must have: 'subject', 'relation', 'object', 'claim_type'. "
                "Set 'claim_type' to the relation name if it fits."
            )
            res = pipeline.verify_statement(claim, custom_system_prompt=metaqa_prompt)
        return res["overall_verdict"]

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
        res = pipeline.verify_with_context(claim, triples, custom_system_prompt=factkg_prompt)
    else:
        res = pipeline.verify_statement(claim)
        
    return res["overall_verdict"]

def main():
    parser = argparse.ArgumentParser(description="Public Fact Verification Baseline Evaluation Harness")
    parser.add_argument("--dataset", type=str, default="factkg", choices=["factkg", "fever", "codex", "metaqa", "nusmods"], help="Dataset to run on")
    parser.add_argument("--method", type=str, default="pipeline", choices=["closed_book_llm", "context_llm", "pipeline"], help="Verification method")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of items to evaluate")
    parser.add_argument("--model_name", type=str, default=None, help="LLM model name (e.g. azure-4.1-mini, azure-5-mini, google/gemma-4-e4b)")
    parser.add_argument("--provider", type=str, default=None, choices=["azure", "local"], help="LLM provider")
    parser.add_argument("--oracle_linking", action="store_true", help="Enable Experiment 1: Oracle Entity/Relation Linking")
    parser.add_argument("--decontextualize", action="store_true", help="Enable Experiment 3: CoVe-style factored multi-hop decontextualization")
    parser.add_argument("--smooth_calibration", action="store_true", help="Enable Experiment 4: Continuous confidence score calibration & smoothing")
    parser.add_argument("--output_file", type=str, default=None, help="Path to write JSON evaluation output")
    parser.add_argument("--max_workers", type=int, default=10, help="Number of parallel worker threads for LLM calls")
    parser.add_argument("--sample", type=str, default="random", choices=["prefix", "random"],
                        help="Row selection. 'prefix' takes the first --limit rows; several benchmark files "
                             "are ordered by reasoning type or label, which makes prefix sampling non-representative.")
    parser.add_argument("--sample_seed", type=int, default=20260725, help="Seed for --sample random")
    parser.add_argument("--withhold_unresolved_claims", action="store_true",
                        help="Ablation: withhold claims whose subject could not be linked from the "
                             "verdict vote. Off by default — measured at +0.8 pts on CoDEx (inside "
                             "the noise floor) against -2.67 pts on RMIT.")
    parser.add_argument("--entity_link_threshold", type=float, default=None,
                        help="Minimum bi-encoder cosine score to accept an entity link. Below it, the subject "
                             "is treated as unresolved (routing to Not-in-KG) rather than linked to a wrong entity.")
    parser.add_argument("--routing_mode", type=str, default=None,
                        choices=["dynamic", "fixed_cwa", "fixed_owa"],
                        help="World-assumption dispatch (E2 ablation arm). 'dynamic' routes per relation on "
                             "estimated occupancy against --cwa_threshold; 'fixed_cwa'/'fixed_owa' pin every "
                             "relation to one assumption. Default: the pipeline's own default (dynamic).")
    parser.add_argument("--cwa_threshold", type=float, default=None,
                        help="Occupancy at or above which a relation is treated as closed-world under "
                             "--routing_mode dynamic. Swept 0.50-0.95 in the E2 ablation. Ignored by the "
                             "fixed arms. Note: dynamic routing is only distinguishable from fixed_cwa when "
                             "estimated occupancy actually varies across relations.")
    args = parser.parse_args()

    # Reject structured methods on FEVER
    if args.dataset == "fever" and args.method in ["pipeline", "context_llm"]:
        logger.error("FEVER consists of unstructured text evidence, not structured KG triples. Structured pipeline and context-LLM verification methods are structurally inapplicable on FEVER. Please use closed_book_llm for FEVER, or switch to the factkg dataset.")
        return

    # Get the LLM Client
    llm_client = get_llm_client(provider=args.provider, model=args.model_name)
    
    # Initialize adapter
    if args.dataset == "factkg":
        adapter = FactKGAdapter()
    elif args.dataset == "codex":
        from adapters.codex_adapter import CoDExAdapter
        adapter = CoDExAdapter()
    elif args.dataset == "metaqa":
        from adapters.metaqa_adapter import MetaQAAdapter
        adapter = MetaQAAdapter()
    elif args.dataset == "nusmods":
        from adapters.nusmods_adapter import NusmodsAdapter
        adapter = NusmodsAdapter()
    else:
        adapter = FEVERAdapter()
        
    data = adapter.load_data()
    if args.sample == "random" and args.limit < len(data):
        # Several benchmark files are ordered (FactKG is sorted into contiguous reasoning-type
        # blocks), so data[:limit] is not a sample. Draw without replacement under a recorded seed.
        rng = random.Random(args.sample_seed)
        data = [data[i] for i in sorted(rng.sample(range(len(data)), args.limit))]
        logger.info(f"Sampled {len(data)} rows at random (seed={args.sample_seed}).")
    else:
        data = data[:args.limit]
        if args.sample == "prefix":
            logger.warning("Using prefix sampling; the evaluated rows may not be representative.")

    pipeline_kwargs = dict(
        llm_client=llm_client,
        oracle_linking=args.oracle_linking,
        decontextualize=args.decontextualize,
        smooth_calibration=args.smooth_calibration,
        withhold_unresolved_claims=args.withhold_unresolved_claims,
    )
    if args.entity_link_threshold is not None:
        pipeline_kwargs["entity_link_threshold"] = args.entity_link_threshold
    if args.routing_mode is not None:
        pipeline_kwargs["routing_mode"] = args.routing_mode
    if args.cwa_threshold is not None:
        pipeline_kwargs["cwa_threshold"] = args.cwa_threshold

    pipeline = None
    if args.method == "pipeline":
        if args.dataset == "codex":
            pipeline = VerificationPipeline(kg_path="data/codex_graph.json", **pipeline_kwargs)
        elif args.dataset == "metaqa":
            pipeline = VerificationPipeline(kg_path="data/metaqa_graph.json", **pipeline_kwargs)
        elif args.dataset == "nusmods":
            pipeline = VerificationPipeline(kg_path="data/nusmods_graph.json", **pipeline_kwargs)
        else:
            pipeline = VerificationPipeline(**pipeline_kwargs)


    logger.info(f"Running evaluation on {len(data)} items from {args.dataset} using {args.method} (Model: {llm_client.model}, Provider: {llm_client.provider}, Max Workers: {args.max_workers})...")
    
    predictions = [None] * len(data)
    gold_labels = [None] * len(data)
    results_detail = [None] * len(data)

    def evaluate_item(idx, item):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])

        row_started = time.perf_counter()
        with llm_client.usage.scope() as row_usage:
            if args.method == "closed_book_llm":
                pred = run_closed_book_verification(claim, llm_client)
            elif args.method == "pipeline":
                pred = run_pipeline_verification(claim, triples, pipeline, args.dataset)
            else:
                pred = run_context_verification(claim, triples, llm_client)
        row_usage = dict(row_usage, wall_clock_s=time.perf_counter() - row_started)
        raw_pred = pred


        # Normalize prediction label space based on the dataset
        if args.dataset == "factkg":
            if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                pred = "Contradicted"
            elif pred != "Supported":
                pred = "Contradicted"
        elif args.dataset in ["codex", "metaqa", "nusmods"]:
            if pred == "Out-of-scope":
                pred = "Not-in-KG"
                
        return idx, pred, gold, raw_pred, {
            "id": item["id"],
            "claim": claim,
            "gold": gold,
            "pred": pred,
            "raw_pred": raw_pred,
            "reasoning_type": item.get("reasoning_type", "N/A"),
            "usage": row_usage
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(evaluate_item, idx, item): idx for idx, item in enumerate(data)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                i, pred, gold, raw_pred, detail = future.result()
                predictions[i] = pred
                gold_labels[i] = gold
                results_detail[i] = detail
            except Exception as e:
                # A crash is NOT a prediction. Leave the slot unscored (None) instead of
                # substituting a default label, which would credit the run whenever that
                # default happens to match the gold label.
                logger.error(f"Error evaluating item {idx}: {e}")
                predictions[idx] = None
                gold_labels[idx] = data[idx]["gold_label"]
                results_detail[idx] = {
                    "id": data[idx]["id"],
                    "claim": data[idx]["text"],
                    "gold": data[idx]["gold_label"],
                    "pred": None,
                    "raw_pred": "Error",
                    "error": str(e),
                    "reasoning_type": data[idx].get("reasoning_type", "N/A")
                }

        
    # Compute metrics (crashes are excluded from the denominator, not defaulted to a label)
    accuracy, class_metrics, ci_lower, ci_upper, n_scored = compute_metrics(predictions, gold_labels)
    n_errors = len(data) - n_scored
    run_usage = llm_client.usage.snapshot()
    run_usage["per_row"] = {
        "n_rows": len(data),
        "tokens_per_row": (run_usage["total_tokens"] / len(data)) if data else None,
        "calls_per_row": (run_usage["n_calls"] / len(data)) if data else None,
    }

    # Print results
    print("\n" + "="*60)
    print(f"EVALUATION REPORT: {args.dataset.upper()} - {args.method.upper()} (Model: {llm_client.model})")
    print("="*60)
    print(f"Total Items: {len(data)}")
    print(f"Scored: {n_scored}   Unscored (call raised): {n_errors}")
    print(f"Accuracy (over scored rows): {accuracy:.2%} (95% CI: [{ci_lower:.2%}, {ci_upper:.2%}])")
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

    coverage, selective_accuracy = 1.0, accuracy
    if args.method == "pipeline" and args.dataset == "factkg":
        covered_items = [r for r in results_detail if r["raw_pred"] in ["Supported", "Contradicted"]]
        coverage = len(covered_items) / len(results_detail) if results_detail else 0.0
        covered_correct = sum(1 for r in covered_items if r["pred"] == r["gold"])
        selective_accuracy = covered_correct / len(covered_items) if covered_items else 0.0
        print(f"Coverage (In-Scope Claims): {coverage:.2%}")
        print(f"Selective Accuracy (On Covered Subset): {selective_accuracy:.2%}\n")

    # Tri-state view: scored alongside the forced-binary protocol rather than replacing it.
    # The forced-binary mapping collapses Not-in-KG/Out-of-scope/Abstained into Contradicted,
    # which makes abstention unmeasurable; this block preserves the distinction.
    tristate = None
    if args.method == "pipeline":
        decisions = ["Supported", "Contradicted", "Not-in-KG"]
        tri_rows = [r for r in results_detail if r["raw_pred"] != "Error"]
        tri_cov = [r for r in tri_rows if r["raw_pred"] in decisions]
        tri_correct = sum(1 for r in tri_cov if r["raw_pred"] == r["gold"])
        tristate = {
            "n_scored": len(tri_rows),
            "coverage": len(tri_cov) / len(tri_rows) if tri_rows else 0.0,
            "selective_accuracy": tri_correct / len(tri_cov) if tri_cov else 0.0,
            "abstention_rate": 1 - (len(tri_cov) / len(tri_rows)) if tri_rows else 0.0,
            "raw_verdict_distribution": {
                v: sum(1 for r in tri_rows if r["raw_pred"] == v)
                for v in sorted({r["raw_pred"] for r in tri_rows})
            },
        }
        print(f"Tri-state (raw verdicts, pre-collapse): coverage {tristate['coverage']:.2%}, "
              f"selective accuracy {tristate['selective_accuracy']:.2%}")
        print(f"  raw verdicts: {tristate['raw_verdict_distribution']}\n")


    headers = ["Class", "Precision", "Recall", "F1-Score", "Support"]
    print_markdown_table(headers, class_metrics)
    
    # Reasoning type breakdown. NUSMods rows carry a reasoning type that identifies the item
    # construction (credit-one-hop, absent-module-*, ...), so the same breakdown applies there.
    if args.dataset in ["factkg", "nusmods"]:
        print("\nReasoning Type Breakdown:")
        reasoning_types = set(item["reasoning_type"] for item in results_detail)
        r_rows = []
        for r_type in sorted(reasoning_types):
            # Unscored rows are excluded here for the same reason compute_metrics excludes them:
            # a crashed row is not a wrong prediction, and counting it as one understates the
            # per-type accuracy by a different amount in every type.
            r_items = [item for item in results_detail
                       if item["reasoning_type"] == r_type and item["pred"] is not None]
            r_correct = sum(1 for item in r_items if item["pred"] == item["gold"])
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

    # Save output file if specified
    if args.output_file:
        os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
        out_data = {
            "dataset": args.dataset,
            "method": args.method,
            "model_name": llm_client.model,
            "provider": llm_client.provider,
            "oracle_linking": args.oracle_linking,
            "decontextualize": args.decontextualize,
            "smooth_calibration": args.smooth_calibration,
            "total_evaluated": len(data),
            "n_scored": n_scored,
            "n_unscored_errors": n_errors,
            "sampling": args.sample,
            "sample_seed": args.sample_seed,
            "entity_link_threshold": args.entity_link_threshold,
            "routing_mode": args.routing_mode,
            "cwa_threshold": args.cwa_threshold,
            "accuracy": accuracy,
            "ci_95": [ci_lower, ci_upper],
            "coverage": coverage,
            "selective_accuracy": selective_accuracy,
            "tristate": tristate,
            "usage": run_usage,
            "results_detail": results_detail
        }
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        logger.info(f"Saved benchmark results to {args.output_file}")

if __name__ == "__main__":
    main()
