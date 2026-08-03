"""Generate a deterministic, schema-diverse question set for long-form answer experiments."""

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


DEFAULT_COUNTS = {
    "scalar-credit": 8,
    "set-membership-term": 8,
    "prerequisite-existence": 8,
    "preclusion-existence": 8,
    "conjunction": 8,
    "prerequisite-exhaustiveness": 6,
    "prerequisite-multi-hop": 6,
    "mixed-fact-advice": 6,
    "staffing-open-world": 8,
}


def counts_for_total(total, weights=None):
    """Allocate an exact requested total across question types deterministically."""
    if total < 1:
        raise ValueError("question count must be positive")
    weights = weights or DEFAULT_COUNTS
    weight_total = sum(weights.values())
    raw = {name: total * weight / weight_total for name, weight in weights.items()}
    counts = {name: int(value) for name, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(weights, key=lambda name: (-(raw[name] - counts[name]), name))
    for name in order[:remainder]:
        counts[name] += 1
    return counts


def _prerequisites(record):
    return [
        str(item.get("course_id") if isinstance(item, dict) else item)
        for item in record.get("prerequisites", [])
    ]


def build_questions(graph, seed=20260802, counts=None):
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
        raise RuntimeError("Question pool exhausted")

    credits = pool(lambda r: r.get("credits") is not None)
    terms = pool(lambda r: bool(r.get("semesters")))
    any_prereqs = pool(lambda r: bool(_prerequisites(r)))
    no_prereqs = pool(lambda r: "prerequisites" in r and not _prerequisites(r))
    one_prereq = pool(lambda r: len(_prerequisites(r)) == 1)
    many_prereqs = pool(lambda r: len(_prerequisites(r)) > 1)
    any_preclusions = pool(lambda r: bool(r.get("preclusions")))
    no_preclusions = pool(lambda r: "preclusions" in r and not r.get("preclusions"))
    conjunctions = pool(lambda r: r.get("credits") is not None and r.get("school"))
    staffing = pool(lambda r: r.get("credits") is not None)
    chains = [
        (code, intermediate, target)
        for code, record in graph.items()
        for intermediate in _prerequisites(record)
        for target in _prerequisites(graph.get(intermediate, {}))
        if intermediate in graph
    ]
    rng.shuffle(chains)

    rows = []

    def emit(question_type, code, question, evidence, expected):
        record = graph[code]
        rows.append({
            "id": f"nq-{len(rows) + 1:04d}",
            "question_type": question_type,
            "subject": code,
            "subject_title": record.get("title", code),
            "question": question,
            "evidence_triples": evidence,
            "expected_triples": expected,
        })

    for _ in range(counts["scalar-credit"]):
        code = take(credits)
        value = str(graph[code]["credits"])
        emit("scalar-credit", code, f"How many modular credits is {code} worth?",
             [[code, "hasCreditValue", value]], [[code, "hasCreditValue", value]])

    for _ in range(counts["set-membership-term"]):
        code = take(terms)
        semester = rng.choice(graph[code]["semesters"])
        emit("set-membership-term", code,
             f"Is {code} offered in Semester {semester}? Explain briefly.",
             [[code, "offeredInTerm", str(value)] for value in graph[code]["semesters"]],
             [[code, "offeredInTerm", str(semester)]])

    for index in range(counts["prerequisite-existence"]):
        source = any_prereqs if index % 2 == 0 else no_prereqs
        code = take(source)
        prereqs = _prerequisites(graph[code])
        evidence = [[code, "requiresPrerequisite", value] for value in prereqs]
        expected = evidence if prereqs else [[code, "requiresPrerequisite", "none"]]
        emit("prerequisite-existence", code,
             f"Does {code} have any prerequisite modules? State the answer in a complete sentence.",
             evidence, expected)

    for index in range(counts.get("preclusion-existence", 0)):
        source = any_preclusions if index % 2 == 0 else no_preclusions
        code = take(source)
        preclusions = [str(value) for value in graph[code].get("preclusions", [])]
        evidence = [[code, "preclusions", value] for value in preclusions]
        expected = evidence if preclusions else [[code, "preclusions", "none"]]
        emit("preclusion-existence", code,
             f"Does {code} have any precluded modules? State the answer in a complete sentence.",
             evidence, expected)

    for _ in range(counts["conjunction"]):
        code = take(conjunctions)
        record = graph[code]
        evidence = [
            [code, "hasCreditValue", str(record["credits"])],
            [code, "partOfSchool", record["school"]],
        ]
        emit("conjunction", code,
             f"Which faculty offers {code}, and how many modular credits does it carry?",
             evidence, evidence)

    for index in range(counts["prerequisite-exhaustiveness"]):
        source = one_prereq if index % 2 == 0 else many_prereqs
        code = take(source)
        prereqs = _prerequisites(graph[code])
        candidate = prereqs[0]
        evidence = [[code, "requiresPrerequisite", value] for value in prereqs]
        emit("prerequisite-exhaustiveness", code,
             f"Is {candidate} the only prerequisite module listed for {code}? Explain briefly.",
             evidence, evidence)

    for _ in range(counts["prerequisite-multi-hop"]):
        while chains:
            code, intermediate, target = chains.pop()
            if code not in used:
                used.add(code)
                break
        else:
            raise RuntimeError("Multi-hop question pool exhausted")
        evidence = [
            [code, "requiresPrerequisite", intermediate],
            [intermediate, "requiresPrerequisite", target],
        ]
        emit("prerequisite-multi-hop", code,
             f"Describe one two-step prerequisite path beginning at {code}.", evidence, evidence)

    for _ in range(counts["mixed-fact-advice"]):
        code = take(credits)
        value = str(graph[code]["credits"])
        emit("mixed-fact-advice", code,
             f"How many modular credits is {code} worth, and what general planning advice would you give a student considering it?",
             [[code, "hasCreditValue", value]], [[code, "hasCreditValue", value]])

    for _ in range(counts.get("staffing-open-world", 0)):
        code = take(staffing)
        emit("staffing-open-world", code,
             f"Who teaches or coordinates {code}? State clearly if the catalog does not provide staffing information.",
             [], [[code, "taughtBy", "not specified"]])

    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/nusmods_graph.json")
    parser.add_argument("--out", default="data/nusmods_questions.jsonl")
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    rows = build_questions(graph, args.seed, counts=counts_for_total(args.limit))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    manifest = {
        "seed": args.seed,
        "question_count": len(rows),
        "question_type_distribution": dict(Counter(row["question_type"] for row in rows)),
        "graph": str(args.graph),
        "graph_sha256": hashlib.sha256(Path(args.graph).read_bytes()).hexdigest(),
        "questions_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} questions to {output}")
    print(f"wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()
