"""Generate a deterministic 50-question long-form transfer set over the RMIT graph."""

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


DEFAULT_COUNTS = {
    "prerequisite-multi-hop": 4,
    "scalar-credit": 8,
    "school-lookup": 8,
    "prerequisite-existence": 10,
    "conjunction": 8,
    "coordinator-lookup": 8,
    "mixed-fact-advice": 4,
}


def prerequisites(record):
    return [
        str(item.get("course_id") if isinstance(item, dict) else item)
        for item in record.get("prerequisites", [])
    ]


def build_questions(graph, seed=20260803, counts=None):
    counts = counts or DEFAULT_COUNTS
    rng = random.Random(seed)
    used = set()

    def pool(predicate):
        values = [code for code, record in graph.items() if predicate(record)]
        rng.shuffle(values)
        return values

    def take(values):
        while values:
            code = values.pop()
            if code not in used:
                used.add(code)
                return code
        raise RuntimeError("RMIT question pool exhausted")

    credits = pool(lambda record: record.get("credits") is not None)
    schools = pool(lambda record: bool(record.get("school")))
    coordinators = pool(lambda record: bool(record.get("coordinator")))
    any_prereqs = pool(lambda record: bool(prerequisites(record)))
    no_prereqs = pool(lambda record: "prerequisites" in record and not prerequisites(record))
    conjunctions = pool(lambda record: record.get("credits") is not None and record.get("school"))
    mixed = pool(lambda record: record.get("credits") is not None)
    chains = [
        (code, intermediate, target)
        for code, record in graph.items()
        for intermediate in prerequisites(record)
        for target in prerequisites(graph.get(intermediate, {}))
    ]
    rng.shuffle(chains)

    rows = []

    def emit(question_type, code, question, evidence, expected):
        record = graph[code]
        rows.append({
            "id": f"rq-{len(rows) + 1:04d}",
            "question_type": question_type,
            "subject": code,
            "subject_title": record.get("title", code),
            "question": question,
            "evidence_triples": evidence,
            "expected_triples": expected,
        })

    for _ in range(counts["prerequisite-multi-hop"]):
        while chains:
            code, intermediate, target = chains.pop()
            if code not in used:
                used.add(code)
                break
        else:
            raise RuntimeError("RMIT multi-hop pool exhausted")
        evidence = [
            [code, "requiresPrerequisite", intermediate],
            [intermediate, "requiresPrerequisite", target],
        ]
        emit("prerequisite-multi-hop", code,
             f"Describe one two-step prerequisite path beginning at course {code}.",
             evidence, evidence)

    for _ in range(counts["scalar-credit"]):
        code = take(credits)
        value = str(graph[code]["credits"])
        triple = [[code, "hasCreditValue", value]]
        emit("scalar-credit", code, f"How many credit points is course {code} worth?", triple, triple)

    for _ in range(counts["school-lookup"]):
        code = take(schools)
        value = str(graph[code]["school"])
        triple = [[code, "partOfSchool", value]]
        emit("school-lookup", code, f"Which RMIT school offers course {code}?", triple, triple)

    for index in range(counts["prerequisite-existence"]):
        code = take(any_prereqs if index % 2 == 0 else no_prereqs)
        values = prerequisites(graph[code])
        evidence = [[code, "requiresPrerequisite", value] for value in values]
        expected = evidence if values else [[code, "requiresPrerequisite", "none"]]
        emit("prerequisite-existence", code,
             f"Does course {code} have any prerequisite courses? Answer in a complete sentence.",
             evidence, expected)

    for _ in range(counts["conjunction"]):
        code = take(conjunctions)
        record = graph[code]
        evidence = [
            [code, "hasCreditValue", str(record["credits"])],
            [code, "partOfSchool", str(record["school"])],
        ]
        emit("conjunction", code,
             f"Which RMIT school offers course {code}, and how many credit points is it worth?",
             evidence, evidence)

    for _ in range(counts["coordinator-lookup"]):
        code = take(coordinators)
        value = str(graph[code]["coordinator"])
        triple = [[code, "taughtBy", value]]
        emit("coordinator-lookup", code, f"Who coordinates course {code}?", triple, triple)

    for _ in range(counts["mixed-fact-advice"]):
        code = take(mixed)
        value = str(graph[code]["credits"])
        triple = [[code, "hasCreditValue", value]]
        emit("mixed-fact-advice", code,
             f"How many credit points is course {code} worth, and what general enrolment advice would you give?",
             triple, triple)

    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/rmit_graph.json")
    parser.add_argument("--out", default="data/rmit_questions_50.jsonl")
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()
    graph_path = Path(args.graph)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    rows = build_questions(graph, seed=args.seed)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    manifest = {
        "seed": args.seed,
        "question_count": len(rows),
        "question_type_distribution": dict(Counter(row["question_type"] for row in rows)),
        "graph_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
        "questions_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} RMIT questions to {output}")


if __name__ == "__main__":
    main()
