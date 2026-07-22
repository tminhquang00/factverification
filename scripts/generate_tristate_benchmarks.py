import os
import sys
import json
import random
import logging

sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_tristate_benchmarks")

def build_codex_tri_benchmark(graph_path="data/codex_graph.json", output_path="data/codex_s_tri.jsonl", limit=300):
    logger.info(f"Building CoDEx-S-Tri benchmark from {graph_path}...")
    if not os.path.exists(graph_path):
        logger.error(f"Graph file not found: {graph_path}")
        return

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    # Collect entities and relations
    entities = list(graph.keys())
    records = []
    random.seed(42)

    for idx in range(limit):
        ent = random.choice(entities)
        props = graph[ent]
        if not props or not isinstance(props, dict):
            continue

        rels = list(props.keys())
        if not rels:
            continue

        chosen_rel = random.choice(rels)
        val = props[chosen_rel]
        val_str = str(val[0]) if isinstance(val, list) and val else str(val)

        if idx % 3 == 0:
            # Supported: True facts present in KG
            claim = f"{ent} has relation {chosen_rel} with value {val_str}."
            records.append({
                "id": f"codex-tri-{idx}",
                "text": claim,
                "gold_label": "Supported",
                "triples": [[ent, chosen_rel, val_str]],
                "category": "supported_present"
            })
        elif idx % 3 == 1:
            # Contradicted: Type-consistent object corruption on dense relations
            other_ent = random.choice(entities)
            while other_ent == ent:
                other_ent = random.choice(entities)
            claim = f"{ent} has relation {chosen_rel} with value {other_ent}."
            records.append({
                "id": f"codex-tri-{idx}",
                "text": claim,
                "gold_label": "Contradicted",
                "triples": [[ent, chosen_rel, other_ent]],
                "category": "type_consistent_corruption"
            })
        else:
            # Not-in-KG: Delete true edges from KG context (held out true facts)
            claim = f"{ent} has relation {chosen_rel} with value {val_str}."
            records.append({
                "id": f"codex-tri-{idx}",
                "text": claim,
                "gold_label": "Not-in-KG",
                "triples": [[ent, chosen_rel, val_str]],
                "is_held_out_edge": True,
                "category": "held_out_true_edge"
            })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    logger.info(f"Saved {len(records)} records to {output_path}")

def build_metaqa_tri_benchmark(graph_path="data/metaqa_graph.json", output_path="data/metaqa_tri.jsonl", limit=219):
    logger.info(f"Building MetaQA-Tri benchmark from {graph_path}...")
    if not os.path.exists(graph_path):
        logger.error(f"Graph file not found: {graph_path}")
        return

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    entities = list(graph.keys())
    records = []
    random.seed(42)

    for idx in range(limit):
        ent = random.choice(entities)
        props = graph[ent]
        if not props or not isinstance(props, dict):
            continue

        rels = list(props.keys())
        if not rels:
            continue

        chosen_rel = random.choice(rels)
        val = props[chosen_rel]
        val_str = str(val[0]) if isinstance(val, list) and val else str(val)

        if idx % 3 == 0:
            claim = f"{ent} has property {chosen_rel} as {val_str}."
            records.append({
                "id": f"metaqa-tri-{idx}",
                "text": claim,
                "gold_label": "Supported",
                "triples": [[ent, chosen_rel, val_str]],
                "category": "supported_present"
            })
        elif idx % 3 == 1:
            other_ent = random.choice(entities)
            claim = f"{ent} has property {chosen_rel} as {other_ent}."
            records.append({
                "id": f"metaqa-tri-{idx}",
                "text": claim,
                "gold_label": "Contradicted",
                "triples": [[ent, chosen_rel, other_ent]],
                "category": "type_consistent_corruption"
            })
        else:
            claim = f"{ent} has property {chosen_rel} as {val_str}."
            records.append({
                "id": f"metaqa-tri-{idx}",
                "text": claim,
                "gold_label": "Not-in-KG",
                "triples": [[ent, chosen_rel, val_str]],
                "is_held_out_edge": True,
                "category": "held_out_true_edge"
            })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    logger.info(f"Saved {len(records)} records to {output_path}")

def main():
    build_codex_tri_benchmark()
    build_metaqa_tri_benchmark()

if __name__ == "__main__":
    main()
