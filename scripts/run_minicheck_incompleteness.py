"""Run the binary MiniCheck baseline over controlled graph-deletion conditions.

MiniCheck predicts supported/unsupported, not the pipeline's three-way labels.  The
output therefore preserves its native binary prediction and separately records the
deliberately lossy mapping ``unsupported -> Contradicted`` used to measure how a
binary verifier behaves when evidence is merely absent.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kg_store import get_kg_store
from scripts.run_flat_context_incompleteness import (
    discover_conditions,
    read_jsonl,
    relevant_context,
)
from scripts.run_incompleteness_pilot import mechanical_gold_for_graph


MINICHECK_COMMIT = "b58b9fa69acbd1015ec970fa65dd752413a053d2"


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verbalize_claim(triple):
    subject, relation, obj = (str(value) for value in triple)
    templates = {
        "hasCreditValue": f"{subject} has a credit value of {obj}.",
        "partOfSchool": f"{subject} is part of {obj}.",
        "requiresPrerequisite": (
            f"{subject} has no prerequisites."
            if obj.strip().lower() in {"none", "no", "null"}
            else f"{subject} requires {obj} as a prerequisite."
        ),
        "preclusions": (
            f"{subject} has no preclusions."
            if obj.strip().lower() in {"none", "no", "null"}
            else f"{subject} precludes {obj}."
        ),
        "offeredInTerm": f"{subject} is offered in term {obj}.",
        "taughtBy": f"{subject} is taught by {obj}.",
    }
    return templates.get(relation, f"{subject} {relation} {obj}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="data/nusmods_questions_200.jsonl")
    parser.add_argument("--degradation_dir", nargs="+", required=True)
    parser.add_argument("--graph_filename", default="nusmods_graph.json")
    parser.add_argument("--seeds", type=int, nargs="*")
    parser.add_argument("--retentions", type=int, nargs="*")
    parser.add_argument("--modes", nargs="*", choices=["random", "clustered"])
    parser.add_argument("--model", default="flan-t5-large")
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--inference_chunk_size", type=int, default=256)
    parser.add_argument("--cache_dir", default="output/model_cache/minicheck")
    parser.add_argument("--nltk_dir", default="output/model_cache/nltk")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        import nltk

        nltk_dir = Path(args.nltk_dir).resolve()
        nltk_dir.mkdir(parents=True, exist_ok=True)
        if str(nltk_dir) not in nltk.data.path:
            nltk.data.path.insert(0, str(nltk_dir))
        for package, resource in (
            ("punkt", "tokenizers/punkt"),
            ("punkt_tab", "tokenizers/punkt_tab/english"),
        ):
            try:
                nltk.data.find(resource)
            except LookupError:
                if not nltk.download(package, download_dir=str(nltk_dir), quiet=True):
                    raise RuntimeError(f"failed to download required NLTK resource {package}")
        from minicheck.minicheck import MiniCheck
    except ImportError as exc:
        raise SystemExit(
            "MiniCheck is not installed. Install the pinned experiment dependency from "
            "requirements-experiments.txt."
        ) from exc

    questions = read_jsonl(args.questions)
    triples = []
    seen_triples = set()
    for question in questions:
        for triple in question.get("expected_triples", []):
            key = tuple(str(value) for value in triple)
            if key not in seen_triples:
                triples.append((question["id"], tuple(triple)))
                seen_triples.add(key)

    conditions = discover_conditions(args)
    if not conditions:
        raise ValueError("no degradation conditions matched")
    graph_groups = {}
    for condition in conditions:
        graph_groups.setdefault(condition["graph_sha256"], []).append(condition)

    tasks = []
    graph_cache = {}
    store_cache = {}
    for graph_hash, aliases in graph_groups.items():
        representative = aliases[0]
        graph = json.loads(Path(representative["graph_path"]).read_text(encoding="utf-8"))
        store = get_kg_store(representative["graph_path"], representative["declaration_path"])
        graph_cache[graph_hash] = graph
        store_cache[graph_hash] = store
        for question_id, triple in triples:
            tasks.append({
                "graph_hash": graph_hash,
                "question_id": question_id,
                "triple": triple,
                "document": relevant_context(graph, triple),
                "claim": verbalize_claim(triple),
            })

    task_fingerprint = hashlib.sha256(json.dumps([
        (task["graph_hash"], task["question_id"], task["triple"], task["document"], task["claim"])
        for task in tasks
    ], sort_keys=True).encode("utf-8")).hexdigest()
    checkpoint_path = Path(args.output).with_suffix(".checkpoint.json")
    labels = []
    support_probabilities = []
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if (
            checkpoint.get("task_fingerprint") == task_fingerprint
            and checkpoint.get("model") == args.model
        ):
            labels = [int(value) for value in checkpoint.get("labels", [])]
            support_probabilities = [
                float(value) for value in checkpoint.get("support_probabilities", [])
            ]
            if len(labels) != len(support_probabilities):
                raise ValueError("MiniCheck checkpoint label/probability lengths differ")

    started = time.time()
    scorer = MiniCheck(
        model_name=args.model,
        batch_size=args.batch_size,
        cache_dir=args.cache_dir,
    )
    for start in range(len(labels), len(tasks), args.inference_chunk_size):
        batch = tasks[start:start + args.inference_chunk_size]
        batch_labels, batch_probabilities, _chunks, _chunk_probabilities = scorer.score(
            docs=[task["document"] for task in batch],
            claims=[task["claim"] for task in batch],
        )
        labels.extend(int(value) for value in batch_labels)
        support_probabilities.extend(float(value) for value in batch_probabilities)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(json.dumps({
            "model": args.model,
            "task_fingerprint": task_fingerprint,
            "completed": len(labels),
            "expected": len(tasks),
            "labels": labels,
            "support_probabilities": support_probabilities,
        }, indent=2), encoding="utf-8")

    rows = []
    for task, label, probability in zip(tasks, labels, support_probabilities):
        graph = graph_cache[task["graph_hash"]]
        store = store_cache[task["graph_hash"]]
        gold = mechanical_gold_for_graph(task["triple"], graph, store)
        native_prediction = "Supported" if int(label) == 1 else "Unsupported"
        mapped_prediction = "Supported" if int(label) == 1 else "Contradicted"
        for condition in graph_groups[task["graph_hash"]]:
            rows.append({
                "model": f"MiniCheck-{args.model}",
                "question_id": task["question_id"],
                "seed": condition["seed"],
                "mode": condition["mode"],
                "retention": condition["retention"],
                "triple": list(task["triple"]),
                "claim": task["claim"],
                "document": task["document"],
                "gold": gold,
                "binary_gold": "Supported" if gold == "Supported" else "Unsupported",
                "native_prediction": native_prediction,
                "mapped_prediction": mapped_prediction,
                "support_probability": float(probability),
                "graph_sha256": task["graph_hash"],
            })

    output = {
        "run": {
            "model": f"MiniCheck-{args.model}",
            "minicheck_commit": MINICHECK_COMMIT,
            "question_count": len(questions),
            "unique_triples": len(triples),
            "unique_graphs": len(graph_groups),
            "condition_count": len(conditions),
            "inference_pair_count": len(tasks),
            "elapsed_seconds": time.time() - started,
            "questions_sha256": file_sha256(args.questions),
            "script_sha256": file_sha256(__file__),
            "binary_limitation": (
                "MiniCheck has no Not-in-KG label; unsupported is mapped to Contradicted only "
                "for the tri-state false-contradiction diagnostic."
            ),
        },
        "rows": rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["run"], indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
