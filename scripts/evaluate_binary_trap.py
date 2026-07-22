import os
import sys
import json
import logging
import numpy as np

sys.path.append(os.getcwd())

from verification_pipeline import VerificationPipeline
from adapters.factkg_adapter import FactKGAdapter
from eval_harness import run_pipeline_verification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_binary_trap")

def evaluate_binary_trap():
    logger.info("Evaluating E7 Binary Benchmark Trap...")
    os.makedirs("output/experiments", exist_ok=True)

    # Load FactKG data
    adapter = FactKGAdapter()
    factkg_data = adapter.load_data()[:500]

    pipeline = VerificationPipeline()

    penalized_abstentions = 0
    genuine_lacks = 0

    for idx, item in enumerate(factkg_data):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])

        raw_pred = run_pipeline_verification(claim, triples, pipeline, "factkg")

        # Under forced-binary scoring, Not-in-KG / Abstained becomes Contradicted
        if raw_pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
            penalized_abstentions += 1
            # Check if KG genuinely lacks the fact
            if gold == "Not-in-KG" or not triples:
                genuine_lacks += 1

    ratio = genuine_lacks / max(1, penalized_abstentions)
    logger.info(f"Total penalized abstentions: {penalized_abstentions}, Genuine lacks: {genuine_lacks}, Ratio: {ratio:.4f}")

    results = {
        "dataset": "factkg",
        "sample_size": len(factkg_data),
        "penalized_abstentions": penalized_abstentions,
        "genuine_lacks_of_fact": genuine_lacks,
        "justified_refusal_rate": float(ratio),
        "summary": f"{ratio*100:.1f}% of penalized abstentions were correct refusals where the KG lacked sufficient groundings."
    }

    with open("output/experiments/binary_trap_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info("Saved Binary Trap evaluation to output/experiments/binary_trap_results.json")

if __name__ == "__main__":
    evaluate_binary_trap()
