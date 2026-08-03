"""Run the thesis pilot over generated long-form answers and degraded NUSMods evidence."""

import argparse
import copy
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from llm_client import get_llm_client
from kg_store import get_kg_store
from verification_pipeline import VerificationPipeline


GENERATION_CONDITIONS = ("closed_book", "rag_full", "rag_degraded")


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(value):
    return re.sub(r"\s+", " ", str(value).strip().lower())


def normalize_school(value):
    text = normalize(value)
    text = re.sub(
        r"^(school of|faculty of|department of|college of|school|faculty|department|college)\s+",
        "",
        text,
    )
    return re.sub(r"[^a-z0-9]", "", text)


def normalize_person(value):
    text = normalize(value)
    text = re.sub(
        r"^(dr\.?|prof\.?|professor|associate professor|assoc\.?\s*prof\.?)\s+",
        "",
        text,
    )
    return re.sub(r"[^a-z0-9]", "", text)


def graph_fact_present(graph, triple):
    subject, relation, obj = triple
    record = graph.get(str(subject))
    if not record:
        return False
    if relation == "hasCreditValue":
        return record.get("credits") is not None and normalize(record["credits"]) == normalize(obj)
    if relation == "partOfSchool":
        return (
            record.get("school") is not None
            and normalize_school(record["school"]) == normalize_school(obj)
        )
    if relation == "offeredInTerm":
        match = re.search(r"\b([1-4])\b", str(obj))
        term = match.group(1) if match else str(obj).lower().replace("semester", "").strip()
        return term in [str(value) for value in record.get("semesters", [])]
    if relation == "requiresPrerequisite":
        values = [
            str(item.get("course_id") if isinstance(item, dict) else item)
            for item in record.get("prerequisites", [])
        ]
        if obj is not None and normalize(obj) in {"none", "no", "no prerequisites", "null"}:
            return "prerequisites" in record and not values
        if str(obj) in values:
            return True
        return any(
            str(obj) in [
                str(item.get("course_id") if isinstance(item, dict) else item)
                for item in graph.get(intermediate, {}).get("prerequisites", [])
            ]
            for intermediate in values
        )
    if relation == "preclusions":
        values = [
            str(item.get("course_id") if isinstance(item, dict) else item)
            for item in record.get("preclusions", [])
        ]
        if obj is not None and normalize(obj) in {"none", "no", "no preclusions", "null"}:
            return "preclusions" in record and not values
        return str(obj) in values
    if relation == "taughtBy":
        values = [record.get("coordinator"), record.get("coordinator_email")]
        return any(
            value not in (None, "", "Unknown")
            and normalize_person(value) == normalize_person(obj)
            for value in values
        )
    return False


def mechanical_gold_for_graph(triple, graph, store):
    """Derive a verdict from graph contents plus the declared relation semantics.

    This deliberately does not call ``stage_4_verify_triple``. It is the experiment oracle against
    which Stage 4 is measured, keeping implementation output out of gold-label construction.
    """
    subject, relation, obj = triple
    if relation == "unclassified":
        return "Out-of-scope"
    if relation in {"entity_unresolved", "object_unresolved"} or not subject:
        return "Not-in-KG"
    record = graph.get(str(subject))
    if record is None:
        return "Not-in-KG"
    if graph_fact_present(graph, triple):
        return "Supported"

    world = store.get_declared_world_assumption(relation)
    if world is None:
        world = "open"

    if relation == "hasCreditValue":
        present = record.get("credits") not in (None, "", "Unknown")
        return "Contradicted" if present or world == "closed" else "Not-in-KG"
    if relation == "partOfSchool":
        present = record.get("school") not in (None, "", "Unknown")
        return "Contradicted" if present or world == "closed" else "Not-in-KG"
    if relation == "taughtBy":
        present = any(record.get(field) not in (None, "", "Unknown")
                      for field in ("coordinator", "coordinator_email"))
        return "Contradicted" if present or world == "closed" else "Not-in-KG"

    fields = {
        "requiresPrerequisite": "prerequisites",
        "preclusions": "preclusions",
        "offeredInTerm": "semesters",
    }
    if relation in fields:
        field = fields[relation]
        if field not in record:
            return "Contradicted" if world == "closed" else "Not-in-KG"
        values = record.get(field) or []
        negations = {
            "requiresPrerequisite": {"none", "no", "no prerequisites", "no prerequisite", "null"},
            "preclusions": {"none", "no", "no preclusions", "no preclusion", "null"},
            "offeredInTerm": {"none", "no", "no semesters", "null"},
        }
        if obj is not None and normalize(obj) in negations[relation]:
            return "Supported" if not values else "Contradicted"
        return "Contradicted" if world == "closed" else "Not-in-KG"

    if relation in record:
        actual = record.get(relation)
        if isinstance(actual, list):
            matched = any(normalize(value) == normalize(obj) for value in actual)
        else:
            matched = actual not in (None, "", "Unknown") and normalize(actual) == normalize(obj)
        if matched:
            return "Supported"
        return "Contradicted" if world == "closed" else "Not-in-KG"
    return "Not-in-KG"


def context_for_graph(question, graph):
    return [triple for triple in question.get("evidence_triples", []) if graph_fact_present(graph, triple)]


def format_context(triples):
    if not triples:
        return "The retrieval system returned no relevant catalog records."
    return "\n".join(f"- {subject} | {relation} | {obj}" for subject, relation, obj in triples)


def generate_answer(llm_client, question, condition, full_graph, degraded_graph):
    if condition == "closed_book":
        evidence = "No catalog evidence is available. Answer from your own knowledge and say when unsure."
    else:
        graph = full_graph if condition == "rag_full" else degraded_graph
        evidence = "Catalog evidence:\n" + format_context(context_for_graph(question, graph))
    prompt = (
        f"Question: {question['question']}\n\n{evidence}\n\n"
        "Write a natural, self-contained answer of two to four sentences. Separate factual catalog "
        "claims from general advice. Do not mention triples, retrieval, or these instructions."
    )
    for _attempt in range(2):
        answer = llm_client.generate(
            prompt,
            system_prompt="You answer university catalog questions accurately and concisely.",
            temperature=0.2,
            # Gemma 4 exposes a reasoning trace through LM Studio and counts those tokens against
            # max_tokens. A 300-token cap routinely ends before visible content begins.
            max_tokens=1200,
        )
        if answer and answer.strip():
            return answer.strip()
    raise RuntimeError("model returned an empty answer twice")


def aggregate_verdict(verdicts):
    for candidate in ("Contradicted", "Not-in-KG", "Supported", "Out-of-scope"):
        if candidate in verdicts:
            return candidate
    return "Out-of-scope"


def gold_for_degraded(triple, full_result, degraded_graph, degraded_store):
    # ``full_result`` remains in the signature for compatibility with saved-pilot rescoring, but
    # no implementation result participates in the label.
    del full_result
    return mechanical_gold_for_graph(triple, degraded_graph, degraded_store)


def metric_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        for system, prediction in row["predictions"].items():
            grouped[(row["coverage"], row["generation_condition"], system)].append(
                (prediction, row["gold"])
            )
    summary = {}
    for (coverage, condition, system), pairs in sorted(grouped.items()):
        n = len(pairs)
        accuracy = sum(pred == gold for pred, gold in pairs) / n if n else 0.0
        contradicted = [(pred, gold) for pred, gold in pairs if pred == "Contradicted"]
        false_count = sum(gold in {"Supported", "Not-in-KG"} for _pred, gold in contradicted)
        summary[f"coverage_{coverage}__{condition}__{system}"] = {
            "n_atoms": n,
            "accuracy": accuracy,
            "false_contradiction_rate": false_count / len(contradicted) if contradicted else 0.0,
            "n_predicted_contradicted": len(contradicted),
            "n_false_contradictions": false_count,
            "gold_distribution": dict(Counter(gold for _pred, gold in pairs)),
        }
    return summary


def answer_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["generation_condition"]].append(row)
    return {
        condition: {
            "n_answers": len(items),
            "n_generation_or_decomposition_errors": sum(item["error"] is not None for item in items),
            "n_zero_atom_answers": sum(item["n_atoms"] == 0 for item in items),
            "claim_extraction_coverage": (
                sum(item["n_atoms"] > 0 for item in items) / len(items) if items else 0.0
            ),
            "mean_atoms_per_answer": (
                sum(item["n_atoms"] for item in items) / len(items) if items else 0.0
            ),
        }
        for condition, items in sorted(grouped.items())
    }


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="data/nusmods_questions.jsonl")
    parser.add_argument("--full_graph", default="data/nusmods_graph.json")
    parser.add_argument("--full_declaration", default="data/completeness_declarations/nusmods.json")
    parser.add_argument("--degraded_dir", default="output/experiments/nusmods_degradation/random__retention_050")
    parser.add_argument("--degraded_graph_filename", default="nusmods_graph.json")
    parser.add_argument("--provider", required=True, choices=["azure", "local"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--detector_provider", choices=["azure", "local"])
    parser.add_argument("--detector_model")
    parser.add_argument(
        "--reuse_answers",
        help="Reuse the answers in a prior experiment JSON and run only decomposition/verification.",
    )
    parser.add_argument(
        "--reuse_decomposition",
        help=("Reuse claim objects and agreements from a prior experiment JSON, then rerun only "
              "deterministic Stage 3 mapping and verification. Requires --reuse_answers."),
    )
    parser.add_argument(
        "--answer_cache",
        help="Checkpoint generated answers here while the run is in progress.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max_workers", type=int, default=4)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.reuse_decomposition and not args.reuse_answers:
        parser.error("--reuse_decomposition requires --reuse_answers")

    # Capture code identity before any long-running model calls. Reading these files
    # only while writing the final payload can record edits made during the run rather
    # than the implementation the process actually imported.
    script_sha256_at_start = sha256(__file__)
    pipeline_sha256_at_start = sha256("verification_pipeline.py")

    degraded_dir = Path(args.degraded_dir)
    degraded_graph_path = degraded_dir / args.degraded_graph_filename
    degraded_declaration_path = degraded_dir / "completeness.json"
    questions = read_jsonl(args.questions)[:args.limit]
    full_graph = json.loads(Path(args.full_graph).read_text(encoding="utf-8"))
    degraded_graph = json.loads(degraded_graph_path.read_text(encoding="utf-8"))
    detector_provider = args.detector_provider or args.provider
    detector_model = args.detector_model or args.model

    jobs = [(question, condition) for question in questions for condition in GENERATION_CONDITIONS]
    generated = []
    started = time.time()
    generator_client = None
    reused_run = None
    if args.reuse_answers:
        reused_payload = json.loads(Path(args.reuse_answers).read_text(encoding="utf-8"))
        reused_run = reused_payload.get("run", {})
        by_id = {question["id"]: question for question in questions}
        for row in reused_payload.get("answers", []):
            if row["question_id"] not in by_id:
                continue
            generated.append({
                "question": by_id[row["question_id"]],
                "condition": row["generation_condition"],
                "answer": row.get("answer"),
                "error": row.get("error"),
            })
        expected_jobs = {(question["id"], condition) for question, condition in jobs}
        actual_jobs = {(item["question"]["id"], item["condition"]) for item in generated}
        if actual_jobs != expected_jobs:
            missing = sorted(expected_jobs - actual_jobs)[:10]
            raise ValueError(f"Reused answer file does not cover this question set; missing {missing}")
    else:
        generator_client = get_llm_client(provider=args.provider, model=args.model)
        checkpoint_path = Path(args.answer_cache) if args.answer_cache else None
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(
                    generate_answer, generator_client, question, condition,
                    full_graph, degraded_graph,
                ): (question, condition)
                for question, condition in jobs
            }
            for future in as_completed(futures):
                question, condition = futures[future]
                try:
                    generated.append({
                        "question": question, "condition": condition,
                        "answer": future.result(), "error": None,
                    })
                except Exception as exc:
                    generated.append({
                        "question": question, "condition": condition,
                        "answer": None, "error": str(exc),
                    })
                if checkpoint_path and (len(generated) % 10 == 0 or len(generated) == len(jobs)):
                    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                    checkpoint_path.write_text(json.dumps({
                        "provider": args.provider,
                        "model": args.model,
                        "completed": len(generated),
                        "expected": len(jobs),
                        "answers": [
                            {
                                "question_id": item["question"]["id"],
                                "generation_condition": item["condition"],
                                "answer": item["answer"],
                                "error": item["error"],
                            }
                            for item in generated
                        ],
                    }, indent=2), encoding="utf-8")
    generated.sort(key=lambda item: (item["question"]["id"], item["condition"]))

    generation_usage = (
        generator_client.usage.snapshot() if generator_client is not None
        else (reused_run or {}).get("generator_usage", (reused_run or {}).get("usage"))
    )

    if (not args.reuse_answers and detector_provider == args.provider
            and detector_model == args.model):
        detector_client = generator_client
        # Preserve the generation snapshot above, then meter decomposition independently.
        detector_client.usage.reset()
    else:
        detector_client = get_llm_client(provider=detector_provider, model=detector_model)

    full_pipeline = VerificationPipeline(
        kg_path=args.full_graph, completeness_path=args.full_declaration,
        llm_client=detector_client, routing_mode="declared", entity_link_threshold=0.95,
        enable_dense_linking=False,
    )

    def variant(graph_path, declaration_path, routing_mode):
        pipeline = copy.copy(full_pipeline)
        pipeline.store = get_kg_store(str(graph_path), completeness_path=str(declaration_path))
        pipeline.routing_mode = routing_mode
        return pipeline

    degraded_declared = variant(degraded_graph_path, degraded_declaration_path, "declared")
    degraded_occupancy = variant(degraded_graph_path, degraded_declaration_path, "occupancy")
    full_occupancy = variant(args.full_graph, args.full_declaration, "occupancy")

    reused_atoms = {}
    reused_decomposition_run = None
    if args.reuse_decomposition:
        reused_decomposition_payload = json.loads(
            Path(args.reuse_decomposition).read_text(encoding="utf-8")
        )
        reused_decomposition_run = reused_decomposition_payload.get("run", {})
        for row in reused_decomposition_payload.get("atomic_results", []):
            key = (row["question_id"], row["generation_condition"], row["atom_index"])
            reused_atoms.setdefault(key, {
                "claim": row["claim"],
                "agreement": row.get("decomposition_agreement", 1.0),
            })
        expected_answers = {
            (item["question"]["id"], item["condition"]) for item in generated
        }
        available_answers = {(qid, condition) for qid, condition, _index in reused_atoms}
        if not available_answers <= expected_answers:
            raise ValueError("Reused decomposition contains answers outside the requested set")

    def decompose_item(item):
        if item["error"] or not item["answer"]:
            return item, [], item["error"] or "missing answer"
        try:
            key_prefix = (item["question"]["id"], item["condition"])
            saved = [
                (key[2], value) for key, value in reused_atoms.items()
                if key[:2] == key_prefix
            ] if args.reuse_decomposition else []
            if args.reuse_decomposition:
                claims_with_agreement = [
                    (value["claim"], value["agreement"])
                    for _index, value in sorted(saved)
                ]
            else:
                claims, agreement = full_pipeline.stage_2_decompose(
                    item["answer"], include_metadata=True
                )
                claims_with_agreement = [(claim, agreement) for claim in claims]
            atoms = []
            for claim, agreement in claims_with_agreement:
                triple, score = full_pipeline.stage_3_map_claim_to_triple(claim, include_metadata=True)
                atoms.append({"claim": claim, "triple": triple, "entity_score": score, "agreement": agreement})
            return item, atoms, None
        except Exception as exc:
            return item, [], str(exc)

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(decompose_item, item) for item in generated]
        decomposed = [future.result() for future in as_completed(futures)]
    decomposed.sort(key=lambda value: (value[0]["question"]["id"], value[0]["condition"]))

    atomic_rows = []
    answer_rows = []
    for item, atoms, error in decomposed:
        answer_verdicts = defaultdict(list)
        for atom_index, atom in enumerate(atoms):
            triple = atom["triple"]
            full_result = mechanical_gold_for_graph(triple, full_graph, full_pipeline.store)
            for coverage, graph, declared_pipeline, occupancy_pipeline in (
                (100, full_graph, full_pipeline, full_occupancy),
                (50, degraded_graph, degraded_declared, degraded_occupancy),
            ):
                gold = full_result if coverage == 100 else gold_for_degraded(
                    triple, full_result, graph, declared_pipeline.store
                )
                declared_pred = declared_pipeline.stage_4_verify_triple(*triple)["verdict"]
                occupancy_pred = occupancy_pipeline.stage_4_verify_triple(*triple)["verdict"]
                predictions = {
                    "declared": declared_pred,
                    "occupancy": occupancy_pred,
                    "binary": "Contradicted" if declared_pred == "Not-in-KG" else declared_pred,
                }
                confidences = {
                    "declared": declared_pipeline.calculate_confidence(
                        *triple, declared_pred,
                        entity_score=atom["entity_score"], decomp_agreement=atom["agreement"],
                    ),
                    "occupancy": occupancy_pipeline.calculate_confidence(
                        *triple, occupancy_pred,
                        entity_score=atom["entity_score"], decomp_agreement=atom["agreement"],
                    ),
                }
                confidences["binary"] = declared_pipeline.calculate_confidence(
                    *triple, predictions["binary"],
                    entity_score=atom["entity_score"], decomp_agreement=atom["agreement"],
                )
                atomic_rows.append({
                    "question_id": item["question"]["id"],
                    "question_type": item["question"]["question_type"],
                    "generation_condition": item["condition"],
                    "coverage": coverage,
                    "atom_index": atom_index,
                    "claim": atom["claim"],
                    "triple": list(triple),
                    "decomposition_agreement": atom["agreement"],
                    "entity_score": atom["entity_score"],
                    "full_graph_verdict": full_result,
                    "gold": gold,
                    "predictions": predictions,
                    "confidences": confidences,
                })
                for system, verdict in predictions.items():
                    answer_verdicts[(coverage, system)].append(verdict)
        answer_rows.append({
            "question_id": item["question"]["id"],
            "question_type": item["question"]["question_type"],
            "question": item["question"]["question"],
            "generation_condition": item["condition"],
            "answer": item["answer"],
            "error": error,
            "n_atoms": len(atoms),
            "answer_predictions": {
                f"coverage_{coverage}__{system}": aggregate_verdict(verdicts)
                for (coverage, system), verdicts in answer_verdicts.items()
            },
        })

    output = {
        "run": {
            "provider": args.provider,
            "model": args.model,
            "generator_model": args.model,
            "generator_provider": args.provider,
            "detector_model": detector_model,
            "detector_provider": detector_provider,
            "same_generator_detector": (
                detector_provider == args.provider and detector_model == args.model
            ),
            "reused_answers_from": args.reuse_answers,
            "reused_decomposition_from": args.reuse_decomposition,
            "mapping_only": bool(args.reuse_decomposition),
            "question_count": len(questions),
            "generation_conditions": list(GENERATION_CONDITIONS),
            "full_graph_sha256": sha256(args.full_graph),
            "degraded_graph_sha256": sha256(degraded_graph_path),
            "questions_sha256": sha256(args.questions),
            "script_sha256": script_sha256_at_start,
            "pipeline_sha256": pipeline_sha256_at_start,
            "elapsed_seconds": time.time() - started,
            "generator_usage": generation_usage,
            "detector_usage": (
                reused_decomposition_run.get("detector_usage")
                if reused_decomposition_run is not None
                else detector_client.usage.snapshot()
            ),
        },
        "summary": metric_summary(atomic_rows),
        "answer_summary": answer_summary(answer_rows),
        "answers": answer_rows,
        "atomic_results": atomic_rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    print(f"saved {output_path}")
    return 0 if all(row["error"] is None for row in answer_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
