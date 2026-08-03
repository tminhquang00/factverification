"""Run a tri-state flat-context LLM verifier over controlled graph-deletion conditions."""

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from kg_store import get_kg_store
from llm_client import get_llm_client
from scripts.run_incompleteness_pilot import mechanical_gold_for_graph


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relevant_context(graph, triple):
    subject, relation, _obj = triple
    record = graph.get(str(subject))
    if record is None:
        return f"No entity record exists for {subject}."
    fields = {
        "hasCreditValue": "credits",
        "partOfSchool": "school",
        "requiresPrerequisite": "prerequisites",
        "preclusions": "preclusions",
        "offeredInTerm": "semesters",
        "taughtBy": "coordinator",
    }
    field = fields.get(relation, relation)
    if field not in record:
        return f"The record for {subject} contains no {field} field."
    value = record.get(field)
    if isinstance(value, list):
        normalized = [
            item.get("course_id") if isinstance(item, dict) else item
            for item in value
        ]
        if not normalized:
            return f"The record explicitly lists an empty {field} set for {subject}."
        return f"The record lists {field} for {subject}: {normalized}."
    if value in (None, "", "Unknown"):
        return f"The {field} value for {subject} is not recorded."
    return f"The record gives {field} for {subject} as: {value}."


def normalize_verdict(value):
    text = str(value or "").strip().lower().replace("_", "-")
    if text in {"supported", "support", "entailment", "entailed"}:
        return "Supported"
    if text in {"contradicted", "contradiction", "refuted", "false"}:
        return "Contradicted"
    if text in {"not-in-kg", "not in kg", "unknown", "insufficient", "nei"}:
        return "Not-in-KG"
    if text in {"out-of-scope", "out of scope"}:
        return "Out-of-scope"
    raise ValueError(f"unrecognized verdict: {value!r}")


def classify(client, triple, context):
    subject, relation, obj = triple
    prompt = (
        f"Claim: ({subject}, {relation}, {obj})\n\nEvidence:\n{context}\n\n"
        "Classify the claim using only the evidence. Use Supported when the evidence explicitly "
        "supports it, Contradicted only when the evidence explicitly conflicts with it, and "
        "Not-in-KG when the evidence is absent or insufficient. Return JSON with keys verdict and reason."
    )
    last_error = None
    for _attempt in range(2):
        try:
            result = client.generate_json(
                prompt,
                system_prompt="You are a conservative evidence-grounded fact verifier.",
                temperature=0.0,
                max_tokens=1200,
            )
            return normalize_verdict(result.get("verdict")), str(result.get("reason", "")), None
        except Exception as exc:
            last_error = str(exc)
    return None, None, last_error


def discover_conditions(args):
    conditions = []
    roots = [Path(value) for value in args.degradation_dir]
    for root in roots:
        for manifest_path in root.rglob("manifest.json"):
            directory = manifest_path.parent
            graph_path = directory / args.graph_filename
            declaration_path = directory / "completeness.json"
            if not graph_path.exists() or not declaration_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Each seed directory also has an aggregate manifest whose values point
            # at the condition manifests.  It is not itself an experiment condition.
            if not {"requested_retention", "seed", "mode", "graph_sha256"} <= manifest.keys():
                continue
            retention = int(round(manifest["requested_retention"] * 100))
            if args.seeds and manifest["seed"] not in args.seeds:
                continue
            if args.retentions and retention not in args.retentions:
                continue
            if args.modes and manifest["mode"] not in args.modes:
                continue
            conditions.append({
                "seed": manifest["seed"],
                "mode": manifest["mode"],
                "retention": retention,
                "graph_path": str(graph_path),
                "declaration_path": str(declaration_path),
                "graph_sha256": manifest["graph_sha256"],
            })
    return sorted(conditions, key=lambda item: (item["seed"], item["mode"], item["retention"]))


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="data/nusmods_questions_200.jsonl")
    parser.add_argument("--degradation_dir", nargs="+", required=True)
    parser.add_argument("--graph_filename", default="nusmods_graph.json")
    parser.add_argument("--provider", required=True, choices=["azure", "local"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--seeds", type=int, nargs="*")
    parser.add_argument("--retentions", type=int, nargs="*")
    parser.add_argument("--modes", nargs="*", choices=["random", "clustered"])
    parser.add_argument("--max_workers", type=int, default=4)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

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
                "context": relevant_context(graph, triple),
            })

    client = get_llm_client(provider=args.provider, model=args.model)
    started = time.time()
    checkpoint = Path(args.output).with_suffix(".checkpoint.json")
    task_fingerprint = hashlib.sha256(json.dumps([
        (task["graph_hash"], task["question_id"], task["triple"], task["context"])
        for task in tasks
    ], sort_keys=True).encode("utf-8")).hexdigest()
    classified = []
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if (
            saved.get("task_fingerprint") == task_fingerprint
            and saved.get("provider") == args.provider
            and saved.get("model") == args.model
        ):
            classified = saved.get("rows", [])
    completed_keys = {
        (row["graph_hash"], row["question_id"], tuple(row["triple"]))
        for row in classified
    }
    remaining_tasks = [
        task for task in tasks
        if (task["graph_hash"], task["question_id"], tuple(task["triple"]))
        not in completed_keys
    ]
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(classify, client, task["triple"], task["context"]): task
            for task in remaining_tasks
        }
        for future in as_completed(futures):
            task = futures[future]
            prediction, reason, error = future.result()
            classified.append({**task, "prediction": prediction, "reason": reason, "error": error})
            if len(classified) % 25 == 0 or len(classified) == len(tasks):
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(json.dumps({
                    "provider": args.provider,
                    "model": args.model,
                    "task_fingerprint": task_fingerprint,
                    "completed": len(classified),
                    "expected": len(tasks),
                    "rows": classified,
                }, indent=2), encoding="utf-8")

    rows = []
    for item in classified:
        graph = graph_cache[item["graph_hash"]]
        store = store_cache[item["graph_hash"]]
        gold = mechanical_gold_for_graph(item["triple"], graph, store)
        for condition in graph_groups[item["graph_hash"]]:
            prediction = item["prediction"]
            rows.append({
                "model": args.model,
                "provider": args.provider,
                "question_id": item["question_id"],
                "seed": condition["seed"],
                "mode": condition["mode"],
                "retention": condition["retention"],
                "triple": list(item["triple"]),
                "gold": gold,
                "prediction": prediction,
                "binary_prediction": (
                    "Contradicted" if prediction == "Not-in-KG" else prediction
                ),
                "reason": item["reason"],
                "error": item["error"],
                "graph_sha256": item["graph_hash"],
            })

    output = {
        "run": {
            "provider": args.provider,
            "model": args.model,
            "question_count": len(questions),
            "unique_triples": len(triples),
            "unique_graphs": len(graph_groups),
            "condition_count": len(conditions),
            "llm_task_count": len(tasks),
            "elapsed_seconds": time.time() - started,
            "questions_sha256": file_sha256(args.questions),
            "script_sha256": file_sha256(__file__),
            "usage": client.usage.snapshot(),
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
