"""Evaluate NUSMods in-KB linking and NIL detection over an entity-held-out split."""

import argparse
import hashlib
import json
import random
import re
import tempfile
from pathlib import Path

import numpy as np

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from verification_pipeline import VerificationPipeline


def title_variant(title):
    words = re.findall(r"[A-Za-z0-9]+", str(title))
    stop = {"a", "an", "and", "for", "in", "of", "the", "to", "with"}
    content = [word for word in words if word.lower() not in stop]
    if len(content) >= 4:
        content = content[1:]
    elif len(content) >= 2:
        content = content[:-1]
    return " ".join(content) or str(title)


def safe_ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def f1(precision, recall):
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def summarize(rows, threshold, active_credits):
    evaluated = []
    for row in rows:
        accepted = row["exact"] or row["score"] >= threshold
        linked = row["candidate"] if accepted else None
        link_correct = linked == row["gold_entity"] if not row["is_nil"] else linked is None
        if linked is None:
            verdict = "Not-in-KG"
        else:
            actual_credit = active_credits.get(linked)
            verdict = "Supported" if str(actual_credit) == str(row["claimed_credit"]) else "Contradicted"
        gold = "Not-in-KG" if row["is_nil"] else "Supported"
        evaluated.append((row, linked, link_correct, verdict, gold))

    in_kb = [item for item in evaluated if not item[0]["is_nil"]]
    nil = [item for item in evaluated if item[0]["is_nil"]]
    correct_links = sum(item[2] for item in in_kb)
    accepted_in_kb = sum(item[1] is not None for item in in_kb)
    nil_rejected = sum(item[1] is None for item in nil)
    in_kb_rejected = sum(item[1] is None for item in in_kb)
    nil_precision = safe_ratio(nil_rejected, nil_rejected + in_kb_rejected)
    nil_recall = safe_ratio(nil_rejected, len(nil))
    in_kb_precision = safe_ratio(correct_links, accepted_in_kb)
    in_kb_recall = safe_ratio(correct_links, len(in_kb))

    contradicted = [item for item in evaluated if item[3] == "Contradicted"]
    false_contradictions = sum(item[4] != "Contradicted" for item in contradicted)
    supported = [item for item in evaluated if item[3] == "Supported"]
    false_supports = sum(item[4] != "Supported" for item in supported)
    return {
        "threshold": threshold,
        "n": len(evaluated),
        "link_accuracy": safe_ratio(sum(item[2] for item in evaluated), len(evaluated)),
        "in_kb_precision": in_kb_precision,
        "in_kb_recall": in_kb_recall,
        "in_kb_f1": f1(in_kb_precision, in_kb_recall),
        "nil_precision": nil_precision,
        "nil_recall": nil_recall,
        "nil_f1": f1(nil_precision, nil_recall),
        "accepted_link_coverage": safe_ratio(sum(item[1] is not None for item in evaluated), len(evaluated)),
        "false_contradiction_rate": safe_ratio(false_contradictions, len(contradicted)),
        "n_predicted_contradicted": len(contradicted),
        "false_support_rate": safe_ratio(false_supports, len(supported)),
        "n_predicted_supported": len(supported),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/nusmods_graph.json")
    parser.add_argument("--sample_per_class", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--thresholds", type=float, nargs="+",
                        default=[0.35, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    graph_path = Path(args.graph)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    codes = sorted(graph)
    rng = random.Random(args.seed)
    rng.shuffle(codes)
    heldout_count = max(args.sample_per_class, len(codes) // 5)
    heldout_codes = set(codes[:heldout_count])
    active = {code: record for code, record in graph.items() if code not in heldout_codes}
    active_codes = [code for code in codes if code in active]
    heldout_codes_list = [code for code in codes if code in heldout_codes]
    rng.shuffle(active_codes)
    rng.shuffle(heldout_codes_list)
    active_sample = active_codes[:args.sample_per_class]
    heldout_sample = heldout_codes_list[:args.sample_per_class]

    samples = []
    for is_nil, selected in ((False, active_sample), (True, heldout_sample)):
        for index, code in enumerate(selected):
            title = graph[code].get("title", code)
            mention = title if index % 2 == 0 else title_variant(title)
            samples.append({
                "mention": mention,
                "gold_entity": code,
                "is_nil": is_nil,
                "claimed_credit": graph[code].get("credits"),
            })

    with tempfile.TemporaryDirectory() as temp_dir:
        active_path = Path(temp_dir) / "active_graph.json"
        active_path.write_text(json.dumps(active), encoding="utf-8")
        pipeline = VerificationPipeline(
            kg_path=str(active_path), llm_client=object(), entity_link_threshold=0.35,
            enable_dense_linking=True,
        )
        nonexact = []
        for sample in samples:
            clean = pipeline.normalize_text(sample["mention"])
            exact_code = pipeline.entity_index.get(clean)
            sample["exact"] = exact_code is not None
            if exact_code is not None:
                sample["candidate"] = exact_code
                sample["score"] = 1.0
            else:
                nonexact.append(sample)

        batch_size = 64
        for start in range(0, len(nonexact), batch_size):
            batch = nonexact[start:start + batch_size]
            queries = pipeline.bi_encoder.encode([row["mention"] for row in batch])
            similarities = np.dot(pipeline.entity_embeddings, queries.T)
            for column, row in enumerate(batch):
                best_index = int(np.argmax(similarities[:, column]))
                row["candidate"] = pipeline.entity_codes_list[best_index]
                row["score"] = float(similarities[best_index, column])

    active_credits = {code: record.get("credits") for code, record in active.items()}
    summaries = [summarize(samples, threshold, active_credits) for threshold in args.thresholds]

    output = {
        "run": {
            "graph": str(args.graph),
            "graph_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
            "seed": args.seed,
            "active_entities": len(active),
            "heldout_entities": len(heldout_codes),
            "sample_per_class": args.sample_per_class,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "thresholds": summaries,
        "rows": samples,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
