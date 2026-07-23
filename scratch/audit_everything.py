import os
import sys
import json
import numpy as np
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.getcwd())

from adapters.factkg_adapter import FactKGAdapter
from adapters.codex_adapter import CoDExAdapter
from adapters.metaqa_adapter import MetaQAAdapter
from adapters.catalog2_adapter import Catalog2Adapter
from verification_pipeline import VerificationPipeline
from eval_harness import run_pipeline_verification

def compute_detailed_stats(predictions, gold_labels):
    n = len(gold_labels)
    unique_labels = ["Supported", "Contradicted", "Not-in-KG"]
    cm = {g: {p: 0 for p in unique_labels} for g in unique_labels}
    for p, g in zip(predictions, gold_labels):
        g_key = g if g in cm else "Not-in-KG"
        p_key = p if p in unique_labels else "Not-in-KG"
        cm[g_key][p_key] += 1

    correct = sum(1 for p, g in zip(predictions, gold_labels) if p == g)
    acc = correct / n if n > 0 else 0.0

    f1s = []
    for c in unique_labels:
        tp = cm[c][c]
        fp = sum(cm[g][c] for g in unique_labels if g != c)
        fn = sum(cm[c][p] for p in unique_labels if p != c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    macro_f1 = float(np.mean(f1s))

    total_pred_contra = sum(cm[g]["Contradicted"] for g in unique_labels)
    false_contra = sum(cm[g]["Contradicted"] for g in ["Supported", "Not-in-KG"])
    fcr_pct = (false_contra / total_pred_contra) if total_pred_contra > 0 else 0.0

    gold_contra = sum(cm["Contradicted"][p] for p in unique_labels)
    contra_rec = (cm["Contradicted"]["Contradicted"] / gold_contra) if gold_contra > 0 else 0.0

    return {
        "n": n,
        "accuracy": acc,
        "macro_f1": macro_f1,
        "confusion_matrix": cm,
        "total_pred_contradictions": total_pred_contra,
        "false_contradictions": false_contra,
        "fcr_fraction": f"{false_contra}/{total_pred_contra}",
        "fcr_pct": fcr_pct,
        "gold_contradictions": gold_contra,
        "contradiction_recall": contra_rec
    }

def main():
    print("=== EXECUTING FAST CONCURRENT METRIC AUDIT ===")

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

    datasets = {
        "RMIT": rmit_data,
        "Catalog2": cat2_data,
        "FactKG": factkg_data,
        "CoDEx-S-Tri": codex_tri_data,
        "MetaQA-Tri": metaqa_tri_data
    }

    label_distributions = {}
    for name, data in datasets.items():
        if not data:
            continue
        golds = [d["gold_label"] for d in data]
        counts = Counter(golds)
        maj = counts.most_common(1)[0]
        maj_acc = maj[1] / len(golds)
        label_distributions[name] = {
            "n": len(golds),
            "counts": dict(counts),
            "majority_class": maj[0],
            "majority_accuracy": float(maj_acc)
        }

    pipeline_rmit = VerificationPipeline(kg_path="data/rmit_graph.json")
    pipeline_cat2 = VerificationPipeline(kg_path="data/catalog2_graph.json")
    pipeline_factkg = VerificationPipeline()
    pipeline_codex = VerificationPipeline(kg_path="data/codex_graph.json")
    pipeline_metaqa = VerificationPipeline(kg_path="data/metaqa_graph.json")

    pipelines = {
        "RMIT": (rmit_data, pipeline_rmit, "rmit"),
        "Catalog2": (cat2_data, pipeline_cat2, "catalog2"),
        "FactKG": (factkg_data, pipeline_factkg, "factkg"),
        "CoDEx-S-Tri": (codex_tri_data, pipeline_codex, "codex"),
        "MetaQA-Tri": (metaqa_tri_data, pipeline_metaqa, "metaqa")
    }

    audit_results = {}

    for ds_name, (data, pipe, mode) in pipelines.items():
        if not data:
            continue
        preds = [None] * len(data)
        golds = [None] * len(data)

        def eval_item(idx, item):
            claim = item["text"]
            gold = item["gold_label"]
            triples = item.get("triples", [])
            pred = run_pipeline_verification(claim, triples, pipe, mode)
            if mode == "factkg":
                if pred in ["Not-in-KG", "Out-of-scope", "Abstained"]:
                    pred = "Contradicted"
                elif pred != "Supported":
                    pred = "Contradicted"
            elif mode in ["codex", "metaqa"]:
                if pred == "Out-of-scope":
                    pred = "Not-in-KG"
            return idx, pred, gold

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(eval_item, idx, item): idx for idx, item in enumerate(data)}
            for future in as_completed(futures):
                i, pred, gold = future.result()
                preds[i] = pred
                golds[i] = gold

        stats = compute_detailed_stats(preds, golds)
        audit_results[ds_name] = stats

    output_data = {
        "label_distributions": label_distributions,
        "metrics": audit_results
    }

    with open("output/complete_audit_metrics.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print("SUCCESS: Saved complete audit metrics to output/complete_audit_metrics.json")

if __name__ == "__main__":
    main()
