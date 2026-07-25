import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_advising_benchmark import _split_for_subject


FIELDNAMES = [
    "course_id",
    "course_title",
    "benchmark_split",
    "query",
    "expected_prerequisite_ids",
    "expected_prerequisite_titles",
    "source_file",
    "source_url",
    "source_accessible",
    "query_scope_valid",
    "expected_set_status",
    "corrected_prerequisite_ids",
    "reviewer_confidence",
    "reviewer_notes",
    "reviewer_id",
    "review_date",
]


def _source_file_for_course(source_dir: Path, course_id: str) -> str:
    matches = sorted(source_dir.glob(f"{course_id}_*.html"))
    return matches[0].as_posix() if matches else ""


def generate_audit_packet(
    graph_path: str,
    source_dir: str,
    output_path: str,
    manifest_path: str,
):
    graph_file = Path(graph_path)
    graph = json.loads(graph_file.read_text(encoding="utf-8"))
    source_directory = Path(source_dir)
    rows = []

    for course_id in sorted(graph):
        course = graph[course_id]
        prerequisites = course.get("prerequisites", [])
        rows.append(
            {
                "course_id": course_id,
                "course_title": course.get("title", ""),
                "benchmark_split": _split_for_subject(course_id),
                "query": f"Which course IDs are listed in the prerequisite section for {course_id}?",
                "expected_prerequisite_ids": "|".join(
                    str(item.get("course_id", "")) for item in prerequisites
                ),
                "expected_prerequisite_titles": "|".join(
                    str(item.get("title", "")) for item in prerequisites
                ),
                "source_file": _source_file_for_course(source_directory, course_id),
                "source_url": (
                    "https://handbook.rmit.edu.au/ords/r/rmit/catalogue/course"
                    f"?p6_code={course_id}"
                ),
                "source_accessible": "",
                "query_scope_valid": "",
                "expected_set_status": "",
                "corrected_prerequisite_ids": "",
                "reviewer_confidence": "",
                "reviewer_notes": "",
                "reviewer_id": "",
                "review_date": "",
            }
        )

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    source_matches = sum(bool(row["source_file"]) for row in rows)
    manifest = {
        "schema_version": 1,
        "audit_packet": "rmit_prerequisite_expected_set_audit_v0",
        "status": "awaiting_single_expert_review",
        "source_graph": graph_path,
        "source_graph_file_hash": f"sha256:{hashlib.sha256(graph_file.read_bytes()).hexdigest()}",
        "source_directory": source_dir,
        "course_count": len(rows),
        "source_file_matches": source_matches,
        "missing_source_files": len(rows) - source_matches,
        "split_counts": dict(sorted(Counter(row["benchmark_split"] for row in rows).items())),
        "output": output_path,
        "review_design": "single_expert_source_audit",
        "allowed_expected_set_status": ["correct", "missing_items", "extra_items", "uncertain"],
        "allowed_reviewer_confidence": ["high", "medium", "low"],
    }
    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate the RMIT expected-set expert audit packet.")
    parser.add_argument("--graph", default="data/rmit_graph.json")
    parser.add_argument("--source-dir", default="output/Study Type/Courses")
    parser.add_argument("--output", default="data/advising/rmit_prerequisite_expected_set_audit_v0.csv")
    parser.add_argument("--manifest", default="data/advising/rmit_prerequisite_expected_set_audit_v0.manifest.json")
    args = parser.parse_args()
    manifest = generate_audit_packet(
        args.graph,
        args.source_dir,
        args.output,
        args.manifest,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()