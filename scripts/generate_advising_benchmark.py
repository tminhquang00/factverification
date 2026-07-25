import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from answer_completeness import AnswerCompletenessVerifier, QueryIntent, QuerySpec
from kg_store import KGStore


def _split_for_subject(subject_id: str) -> str:
    bucket = int(hashlib.sha256(subject_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket < 6:
        return "development"
    if bucket < 8:
        return "calibration"
    return "test"


def _response(subject_id: str, values, condition: str, distractor: str) -> str:
    listed = ", ".join(values)
    if condition == "complete_correct":
        if values:
            return f"The course IDs listed in the prerequisite section for {subject_id} are: {listed}."
        return f"No course IDs are listed in the prerequisite section for {subject_id}."
    if condition == "omit_one":
        retained = values[:-1]
        if retained:
            return f"The prerequisite section for {subject_id} lists: {', '.join(retained)}."
        return f"No course IDs are listed in the prerequisite section for {subject_id}."
    if condition == "omit_multiple":
        return f"No course IDs are listed in the prerequisite section for {subject_id}."
    if condition == "complete_plus_distractor":
        combined = list(values) + [distractor]
        return f"The prerequisite section for {subject_id} lists: {', '.join(combined)}."
    if condition == "corrupted_member":
        corrupted = list(values[:-1]) + [distractor]
        return f"The prerequisite section for {subject_id} lists: {', '.join(corrupted)}."
    raise ValueError(f"Unsupported response condition: {condition}")


def generate_benchmark(graph_path: str, output_path: str, manifest_path: str) -> dict:
    graph_file = Path(graph_path)
    graph_bytes = graph_file.read_bytes()
    graph_data = json.loads(graph_bytes)
    canonical_graph = json.dumps(
        graph_data,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    kg_version = f"sha256:{hashlib.sha256(canonical_graph).hexdigest()}"
    source_file_hash = f"sha256:{hashlib.sha256(graph_bytes).hexdigest()}"
    store = KGStore(str(graph_file))
    verifier = AnswerCompletenessVerifier(store)
    all_subjects = sorted(store.courses)
    records = []

    for subject_id in all_subjects:
        expected = sorted(store.get_prerequisites(subject_id))
        distractor = next(
            (
                candidate
                for candidate in all_subjects
                if candidate != subject_id and candidate not in expected
            ),
            "999999",
        )
        conditions = ["complete_correct", "complete_plus_distractor"]
        if expected:
            conditions.extend(["omit_one", "corrupted_member"])
        if len(expected) >= 2:
            conditions.append("omit_multiple")

        spec = QuerySpec(
            intent=QueryIntent.ALL_PREREQUISITES,
            subject_id=subject_id,
            kg_version=kg_version,
        )
        query = f"Which course IDs are listed in the prerequisite section for {subject_id}?"
        evidence = [
            [subject_id, "requiresPrerequisite", prerequisite]
            for prerequisite in expected
        ]

        for condition in conditions:
            candidate_response = _response(subject_id, expected, condition, distractor)
            result = verifier.verify(spec, candidate_response)
            record_id = f"rmit-prerequisites-{subject_id}-{condition}"
            records.append(
                {
                    "id": record_id,
                    "dataset": "rmit_prerequisite_completeness_v0",
                    "split": _split_for_subject(subject_id),
                    "query": query,
                    "query_spec": {
                        "intent": spec.intent.value,
                        "subject_id": subject_id,
                        "kg_version": kg_version,
                        "scope": {},
                    },
                    "expected_answer_set": expected,
                    "candidate_response": candidate_response,
                    "response_condition": condition,
                    "gold_completeness": result.verdict.value,
                    "gold_missing": sorted(result.missing),
                    "gold_unexpected": sorted(result.unexpected),
                    "gold_set_precision": result.set_precision,
                    "gold_set_recall": result.set_recall,
                    "gold_exact_set_match": result.exact_set_match,
                    "source_evidence": evidence,
                }
            )

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "dataset": "rmit_prerequisite_completeness_v0",
        "status": "synthetic_candidate_not_advisor_audited",
        "source_graph": str(graph_file.as_posix()),
        "source_graph_file_hash": source_file_hash,
        "kg_version": kg_version,
        "record_count": len(records),
        "subject_count": len(all_subjects),
        "split_counts": dict(sorted(Counter(record["split"] for record in records).items())),
        "condition_counts": dict(sorted(Counter(record["response_condition"] for record in records).items())),
        "verdict_counts": dict(sorted(Counter(record["gold_completeness"] for record in records).items())),
        "split_policy": "sha256(subject_id) modulo 10: development=0-5, calibration=6-7, test=8-9",
        "generator": "scripts/generate_advising_benchmark.py",
    }
    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate the set-valued RMIT advising benchmark.")
    parser.add_argument("--graph", default="data/rmit_graph.json")
    parser.add_argument("--output", default="data/advising/rmit_prerequisite_completeness_v0.jsonl")
    parser.add_argument("--manifest", default="data/advising/rmit_prerequisite_completeness_v0.manifest.json")
    args = parser.parse_args()
    manifest = generate_benchmark(args.graph, args.output, args.manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()