"""Compute model-free verification, linking, and full-pipeline attribution metrics."""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kg_store import get_kg_store
from scripts.intervention_gold import intervention_gold
from verification_pipeline import VerificationPipeline


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalize_object(relation, value):
    text = str(value).strip()
    lowered = re.sub(r"\s+", " ", text.lower())
    if relation == "hasCreditValue":
        match = re.search(r"\d+", text)
        return match.group(0) if match else lowered
    if relation == "partOfSchool":
        return re.sub(r"^(faculty|school|department|college)( of)?\s+", "", lowered)
    if relation == "offeredInTerm":
        match = re.search(r"\b([1-4])\b", text)
        return match.group(1) if match else lowered.replace("semester", "").strip()
    if relation in {"requiresPrerequisite", "preclusions"}:
        if lowered in {"none", "no", "null", "no prerequisites", "no preclusions"}:
            return "none"
        return text.upper()
    return lowered


def canonical(triple):
    return (
        str(triple[0]).strip().upper(),
        str(triple[1]).strip(),
        normalize_object(str(triple[1]).strip(), triple[2]),
    )


def ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--declaration", required=True)
    parser.add_argument("--pilots", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    questions = read_jsonl(args.questions)
    question_map = {row["id"]: row for row in questions}
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    pipeline = VerificationPipeline(
        kg_path=args.graph,
        completeness_path=args.declaration,
        llm_client=object(),
        routing_mode="declared",
        entity_link_threshold=0.95,
        enable_dense_linking=False,
    )

    expected_rows = []
    for question in questions:
        for triple in question.get("expected_triples", []):
            # The stage-attribution arms run against the undegraded snapshot, so the reference
            # world and the condition graph are the same object. Gold still comes from the
            # declaration-independent function so that every arm of the study shares one
            # definition of correctness.
            gold = intervention_gold(tuple(triple), graph, graph)["verdict"]
            verification_prediction = pipeline.stage_4_verify_triple(*triple)["verdict"]
            # Generated answers normally mention the course identifier together with
            # its title.  Title-only aliases are often non-unique (for example many
            # modules are named "Special Topics"), so a title-only oracle probe would
            # measure an artificial ambiguity rather than the pipeline's linking stage.
            title = question.get("subject_title") if str(triple[0]) == str(question.get("subject")) else None
            subject_surface = f"{triple[0]} {title}" if title else triple[0]
            claim = {
                "subject": subject_surface,
                "relation": triple[1],
                "object": triple[2],
                "claim_type": triple[1],
            }
            linked, link_score = pipeline.stage_3_map_claim_to_triple(claim, include_metadata=True)
            linked_prediction = pipeline.stage_4_verify_triple(*linked)["verdict"]
            expected_rows.append({
                "question_id": question["id"],
                "question_type": question["question_type"],
                "expected_triple": list(triple),
                "gold": gold,
                "verification_prediction": verification_prediction,
                "linked_triple": list(linked),
                "link_score": link_score,
                "link_correct": canonical(linked) == canonical(triple),
                "linked_prediction": linked_prediction,
            })

    verification_accuracy = ratio(
        sum(row["verification_prediction"] == row["gold"] for row in expected_rows),
        len(expected_rows),
    )
    linking_accuracy = ratio(sum(row["link_correct"] for row in expected_rows), len(expected_rows))
    linked_verification_accuracy = ratio(
        sum(row["linked_prediction"] == row["gold"] for row in expected_rows),
        len(expected_rows),
    )

    run_summaries = []
    for pilot_path in args.pilots:
        payload = json.loads(Path(pilot_path).read_text(encoding="utf-8"))
        atoms = [row for row in payload["atomic_results"] if row["coverage"] == 100]
        extracted = defaultdict(set)
        stage4_pairs = []
        for atom in atoms:
            key = (atom["question_id"], atom["generation_condition"])
            extracted[key].add(canonical(atom["triple"]))
            atom_gold = intervention_gold(tuple(atom["triple"]), graph, graph)["verdict"]
            stage4_pairs.append((atom["predictions"]["declared"], atom_gold))

        condition_metrics = {}
        for condition in sorted({row["generation_condition"] for row in payload["answers"]}):
            true_positive = 0
            extracted_count = 0
            expected_count = 0
            exact = 0
            answer_count = 0
            for answer in payload["answers"]:
                if answer["generation_condition"] != condition:
                    continue
                question = question_map[answer["question_id"]]
                if question["question_type"] == "staffing-open-world":
                    continue
                expected = {canonical(triple) for triple in question.get("expected_triples", [])}
                found = extracted[(answer["question_id"], condition)]
                true_positive += len(expected & found)
                extracted_count += len(found)
                expected_count += len(expected)
                exact += expected == found
                answer_count += 1
            precision = ratio(true_positive, extracted_count)
            recall = ratio(true_positive, expected_count)
            condition_metrics[condition] = {
                "n_answers": answer_count,
                "expected_triple_precision_proxy": precision,
                "expected_triple_recall": recall,
                "expected_triple_f1": (
                    2 * precision * recall / (precision + recall) if precision + recall else 0.0
                ),
                "exact_expected_set_rate": ratio(exact, answer_count),
            }

        run_summaries.append({
            "path": pilot_path,
            "generator_model": payload["run"].get("generator_model", payload["run"]["model"]),
            "detector_model": payload["run"].get("detector_model", payload["run"]["model"]),
            "n_extracted_atoms": len(atoms),
            "stage4_accuracy_on_extracted_atoms": ratio(
                sum(prediction == gold for prediction, gold in stage4_pairs), len(stage4_pairs)
            ),
            "by_generation_condition": condition_metrics,
            "answer_summary": payload["answer_summary"],
        })

    output = {
        "oracle_stages": {
            "n_expected_triples": len(expected_rows),
            "verification_only_accuracy": verification_accuracy,
            "linking_accuracy": linking_accuracy,
            "linking_plus_verification_accuracy": linked_verification_accuracy,
        },
        "runs": run_summaries,
        "expected_rows": expected_rows,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"oracle_stages": output["oracle_stages"], "runs": run_summaries}, indent=2))
    print(f"saved {output_path}")


if __name__ == "__main__":
    main()
