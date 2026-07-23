import os
import sys
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.getcwd())

from adapters.factkg_adapter import FactKGAdapter
from adapters.catalog2_adapter import Catalog2Adapter
from verification_pipeline import VerificationPipeline
from llm_client import LLMClient
from eval_harness import run_pipeline_verification
from scratch.evaluate_single_pass import compute_single_pass_metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("azure_experiments")

MODELS = ["azure-4.1-mini", "azure-5-mini", "azure-4.1"]

def load_all_datasets():
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

    return {
        "RMIT": (rmit_data, "data/rmit_graph.json", "rmit"),
        "Catalog2": (cat2_data, "data/catalog2_graph.json", "catalog2"),
        "FactKG": (factkg_data, "data/rmit_graph.json", "factkg"),
        "CoDEx-S-Tri": (codex_tri_data, "data/codex_graph.json", "codex"),
        "MetaQA-Tri": (metaqa_tri_data, "data/metaqa_graph.json", "metaqa")
    }

def evaluate_model_on_dataset(model_name, dataset_name, dataset_info, max_workers=10):
    data, kg_path, mode = dataset_info
    if not data:
        return None
        
    logger.info(f"Evaluating {model_name} on {dataset_name} ({len(data)} items)...")
    llm_client = LLMClient(provider="azure", model=model_name)
    pipeline = VerificationPipeline(kg_path=kg_path, llm_client=llm_client)

    def process_item(item):
        claim = item["text"]
        triples = item.get("triples", [])
        gold = item["gold_label"]
        pred = run_pipeline_verification(claim, triples, pipeline, mode)
        if mode == "factkg":
            if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                pred = "Contradicted"
            elif pred != "Supported":
                pred = "Contradicted"
        elif mode in ["codex", "metaqa"]:
            if pred == "Out-of-scope":
                pred = "Not-in-KG"
        return pred, gold

    predictions = [None] * len(data)
    gold_labels = [None] * len(data)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(process_item, item): i for i, item in enumerate(data)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                pred, gold = future.result()
                predictions[idx] = pred
                gold_labels[idx] = gold
            except Exception as e:
                logger.error(f"Error processing item {idx} for {model_name}/{dataset_name}: {e}")
                predictions[idx] = "Not-in-KG"
                gold_labels[idx] = data[idx]["gold_label"]

    metrics = compute_single_pass_metrics(predictions, gold_labels)
    logger.info(f"[{model_name} | {dataset_name}] Accuracy: {metrics['accuracy']:.4f}, Macro-F1: {metrics['macro_f1']:.4f}, FCR: {metrics['fcr_fraction']} ({metrics['fcr_pct']*100:.2f}%)")
    return metrics

def main():
    logger.info("Starting Multi-Model Azure OpenAI Evaluation Sweep...")
    datasets = load_all_datasets()
    
    results = {}
    for model_name in MODELS:
        results[model_name] = {}
        for dataset_name, dataset_info in datasets.items():
            metrics = evaluate_model_on_dataset(model_name, dataset_name, dataset_info, max_workers=10)
            if metrics:
                results[model_name][dataset_name] = metrics

    os.makedirs("output/experiments", exist_ok=True)
    out_file = "output/experiments/azure_model_comparison_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Saved Azure Model Comparison Report to {out_file}")

if __name__ == "__main__":
    main()
