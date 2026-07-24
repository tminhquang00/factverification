import os
import sys
import json
import random
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.getcwd())

from adapters.factkg_adapter import FactKGAdapter
from adapters.catalog2_adapter import Catalog2Adapter
from verification_pipeline import VerificationPipeline
from llm_client import LLMClient
from eval_harness import run_pipeline_verification
from scratch.evaluate_single_pass import compute_single_pass_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("full_azure_sweep")

MODELS = ["azure-4.1-mini", "azure-5-mini", "azure-4.1"]

def subject_clustered_bootstrap_ci(predictions, gold_labels, subjects, num_bootstraps=1000, confidence_level=0.95):
    unique_subjects = list(set(subjects))
    n = len(predictions)
    if not unique_subjects or len(unique_subjects) < 5:
        accuracies = []
        for _ in range(num_bootstraps):
            indices = [random.randint(0, n - 1) for _ in range(n)]
            acc = sum(1 for idx in indices if predictions[idx] == gold_labels[idx]) / n
            accuracies.append(acc)
        accuracies.sort()
        low = accuracies[int((1 - confidence_level) / 2 * num_bootstraps)]
        high = accuracies[int((1 + confidence_level) / 2 * num_bootstraps)]
        return round(float(low), 4), round(float(high), 4)

    subj_to_indices = {}
    for idx, s in enumerate(subjects):
        subj_to_indices.setdefault(s, []).append(idx)

    accuracies = []
    num_subjs = len(unique_subjects)

    for _ in range(num_bootstraps):
        sampled_subjs = [random.choice(unique_subjects) for _ in range(num_subjs)]
        sampled_indices = []
        for s in sampled_subjs:
            sampled_indices.extend(subj_to_indices[s])
        if not sampled_indices:
            continue
        acc = sum(1 for idx in sampled_indices if predictions[idx] == gold_labels[idx]) / len(sampled_indices)
        accuracies.append(acc)

    accuracies.sort()
    low = accuracies[int((1 - confidence_level) / 2 * len(accuracies))]
    high = accuracies[int((1 + confidence_level) / 2 * len(accuracies))]
    return round(float(low), 4), round(float(high), 4)

def load_datasets():
    rmit_data = []
    if os.path.exists("data/rmit_test_set.jsonl"):
        with open("data/rmit_test_set.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    g_lbl = item.get("gold_label", item.get("verdict", "Supported"))
                    rmit_data.append({"text": item.get("raw_claim", item["text"]), "gold_label": g_lbl, "triples": item.get("triples", []), "subject": item.get("subject", "rmit")})

    cat2_adapter = Catalog2Adapter()
    cat2_data = cat2_adapter.load_data()[:200]
    for d in cat2_data:
        d["subject"] = d.get("subject", "catalog2")

    factkg_adapter = FactKGAdapter()
    factkg_data = factkg_adapter.load_data()[:500]
    for d in factkg_data:
        d["subject"] = d.get("subject", "factkg")

    codex_data = []
    if os.path.exists("data/codex_s_tri.jsonl"):
        with open("data/codex_s_tri.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    item["subject"] = item.get("subject", "codex")
                    codex_data.append(item)

    metaqa_data = []
    if os.path.exists("data/metaqa_tri.jsonl"):
        with open("data/metaqa_tri.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    item["subject"] = item.get("subject", "metaqa")
                    metaqa_data.append(item)

    return {
        "RMIT": (rmit_data, "data/rmit_graph.json", "rmit"),
        "Catalog2": (cat2_data, "data/catalog2_graph.json", "catalog2"),
        "FactKG": (factkg_data, "data/rmit_graph.json", "factkg"),
        "CoDEx-S-Tri": (codex_data, "data/codex_graph.json", "codex"),
        "MetaQA-Tri": (metaqa_data, "data/metaqa_graph.json", "metaqa")
    }

def run_model_dataset_eval(model_name, dataset_name, dataset_info, max_workers=10):
    data, kg_path, mode = dataset_info
    if not data:
        return None

    logger.info(f"Running Full Experiment for {model_name} on {dataset_name} ({len(data)} items)...")
    llm_client = LLMClient(provider="azure", model=model_name)
    pipeline = VerificationPipeline(kg_path=kg_path, llm_client=llm_client)

    preds = [None] * len(data)
    golds = [None] * len(data)
    subjects = [item.get("subject", dataset_name) for item in data]

    def eval_item(idx, item):
        claim = item["text"]
        gold = item["gold_label"]
        triples = item.get("triples", [])
        pred = run_pipeline_verification(claim, triples, pipeline, mode)
        if mode == "factkg":
            if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                pred = "Contradicted"
            elif pred != "Supported":
                pred = "Contradicted"
        elif mode in ["codex", "metaqa"]:
            if pred == "Out-of-scope":
                pred = "Not-in-KG"
        return idx, pred, gold

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(eval_item, i, item): i for i, item in enumerate(data)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                i, pred, gold = future.result()
                preds[i] = pred
                golds[i] = gold
            except Exception as e:
                logger.error(f"Error evaluating item {idx}: {e}")
                preds[idx] = "Contradicted" if mode == "factkg" else "Not-in-KG"
                golds[idx] = data[idx]["gold_label"]

    metrics = compute_single_pass_metrics(preds, golds)
    ci_low, ci_high = subject_clustered_bootstrap_ci(preds, golds, subjects)
    metrics["ci_95"] = [ci_low, ci_high]
    return metrics

def run_model_e2_routing_sweep(model_name, dataset_name, dataset_info, max_workers=10):
    data, kg_path, mode = dataset_info
    if not data:
        return None

    logger.info(f"Running E2 World-Assumption Routing for {model_name} on {dataset_name}...")
    llm_client = LLMClient(provider="azure", model=model_name)
    pipeline = VerificationPipeline(kg_path=kg_path, llm_client=llm_client)

    e2_results = {}
    for r_mode in ["dynamic", "fixed_cwa", "fixed_owa"]:
        preds = [None] * len(data)
        golds = [None] * len(data)

        def eval_item(idx, item):
            claim = item["text"]
            gold = item["gold_label"]
            triples = item.get("triples", [])
            if r_mode == "fixed_cwa":
                pipeline.cwa_threshold = 0.0
            elif r_mode == "fixed_owa":
                pipeline.cwa_threshold = 1.0
            else:
                pipeline.cwa_threshold = 0.60

            pred = run_pipeline_verification(claim, triples, pipeline, mode)
            if mode == "factkg":
                if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                    pred = "Contradicted"
                elif pred != "Supported":
                    pred = "Contradicted"
            elif mode in ["codex", "metaqa"]:
                if pred == "Out-of-scope":
                    pred = "Not-in-KG"
            return idx, pred, gold

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(eval_item, i, item): i for i, item in enumerate(data)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    i, pred, gold = future.result()
                    preds[i] = pred
                    golds[i] = gold
                except Exception as e:
                    logger.error(f"Error in E2 item {idx}: {e}")
                    preds[idx] = "Contradicted" if mode == "factkg" else "Not-in-KG"
                    golds[idx] = data[idx]["gold_label"]

        metrics = compute_single_pass_metrics(preds, golds)
        e2_results[r_mode] = metrics

    return e2_results

def main():
    logger.info("Starting Master Full Azure OpenAI Multi-Model Experiment Sweep...")
    random.seed(42)
    np.random.seed(42)

    datasets = load_datasets()
    full_report = {}

    for model in MODELS:
        full_report[model] = {
            "headline_l1": {},
            "e2_routing": {}
        }
        for dname, dinfo in datasets.items():
            l1_metrics = run_model_dataset_eval(model, dname, dinfo)
            if l1_metrics:
                full_report[model]["headline_l1"][dname] = l1_metrics

            if dname in ["RMIT", "Catalog2", "FactKG"]:
                e2_metrics = run_model_e2_routing_sweep(model, dname, dinfo)
                if e2_metrics:
                    full_report[model]["e2_routing"][dname] = e2_metrics

    os.makedirs("output/experiments", exist_ok=True)
    out_file = "output/experiments/full_azure_models_experiment_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    logger.info(f"Master Full Azure OpenAI Multi-Model Sweep completed cleanly! Saved to {out_file}")

if __name__ == "__main__":
    main()
