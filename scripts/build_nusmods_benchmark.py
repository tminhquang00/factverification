"""Generate the tri-state NUSMods claim-verification benchmark.

Reads `data/nusmods_graph.json` (built by `scripts/parse_nusmods.py`) and writes
`data/nusmods_test.jsonl`: natural-language claims about NUS modules labelled
`Supported` / `Contradicted` / `Not-in-KG`.

Label convention
----------------
Every gold label is **world-assumption-independent**. That is the design constraint the rest of
the generator follows from, and it exists to keep the benchmark from measuring the verifier's own
routing policy:

* `Supported`    — the catalog states the claimed value.
* `Contradicted` — the catalog states a *conflicting* value for the same single-valued attribute
                   (credits, faculty), or the claim asserts "no prerequisites" for a module whose
                   record names some. A conflict is a conflict under CWA and under OWA alike.
* `Not-in-KG`    — the subject module is absent from the catalog entirely, so no assumption about
                   the completeness of a relation can produce a verdict.

Deliberately excluded: claims of the form "module A requires module B" where A exists, has a
prerequisite rule, and B is not in it. Prerequisite occupancy is 0.31 — the catalog leaves the
field blank for most modules — so the correct label there genuinely depends on whether the
relation is read closed- or open-world. Including such items would make the benchmark score a
routing choice rather than a fact, the same defect that makes `eval_rmit.py` circular.

What this benchmark does and does not establish
-----------------------------------------------
It exercises the full pipeline (LLM decomposition, entity linking, stage-4 dispatch) against a
real institutional catalog of 11,647 modules, with hard negatives drawn from the catalog's own
value distribution so a label-agnostic prior cannot win. It does **not** escape template
derivation: `Supported` claim *content* is interpolated from the same fields the verifier queries,
so a `Supported` item tests decomposition and linking, not catalog comprehension. Phrasings are
varied per item to keep that from collapsing into a single surface pattern.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\build_nusmods_benchmark.py
    & .venv\\Scripts\\python.exe scripts\\build_nusmods_benchmark.py --limit 1000 --seed 7
"""

import argparse
import collections
import json
import logging
import os
import random
import re
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_nusmods_benchmark")

CODE_PARTS = re.compile(r"^([A-Z]+)(\d+)([A-Z]*)$")

# Share of the requested size given to each label, then to each item type within a label.
LABEL_SHARES = {"Supported": 0.34, "Contradicted": 0.33, "Not-in-KG": 0.33}
TYPE_SHARES = {
    "Supported": {
        "credit-one-hop": 0.30,
        "school-one-hop": 0.25,
        "prerequisite-one-hop": 0.20,
        "prerequisite-negation": 0.10,
        "prerequisite-multi-hop": 0.05,
        "conjunction": 0.10,
    },
    "Contradicted": {
        "credit-one-hop": 0.35,
        "school-one-hop": 0.30,
        "prerequisite-negation": 0.20,
        "conjunction": 0.15,
    },
    "Not-in-KG": {
        "absent-module-credit": 0.40,
        "absent-module-school": 0.35,
        "absent-module-prerequisite": 0.25,
    },
}

CREDIT_TEMPLATES = [
    "Module {code} ({title}) is worth {credits} Modular Credits.",
    "NUS module {code} carries {credits} MCs.",
    "{code} {title} is a {credits}-MC module.",
    "Students taking {code} earn {credits} Modular Credits.",
]
SCHOOL_TEMPLATES = [
    "Module {code} ({title}) is offered by {school}.",
    "{code} is taught under {school} at NUS.",
    "The module {code} {title} belongs to {school}.",
    "{school} is the NUS faculty offering {code}.",
]
PREREQUISITE_TEMPLATES = [
    "Module {code} ({title}) requires {prerequisite} as a prerequisite.",
    "To read {code} at NUS a student must first have taken {prerequisite}.",
    "{prerequisite} is listed among the prerequisites of {code}.",
]
NO_PREREQUISITE_TEMPLATES = [
    "Module {code} ({title}) has no prerequisites.",
    "{code} can be read with no prerequisite modules at all.",
    "There are no prerequisite modules listed for {code} {title}.",
]
MULTI_HOP_TEMPLATES = [
    "The prerequisite module of {code} itself requires {target}.",
    "A student reading {code} must have cleared a prerequisite that itself requires {target}.",
]
CONJUNCTION_TEMPLATES = [
    "Module {code} ({title}) is worth {credits} Modular Credits and is offered by {school}.",
    "{code} is a {credits}-MC module taught under {school}.",
    "Offered by {school}, module {code} carries {credits} Modular Credits.",
]


def load_graph(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        graph = json.load(handle)
    if not graph:
        raise ValueError(f"{path} is empty. Run scripts/parse_nusmods.py first.")
    return graph


def value_distributions(graph: Dict[str, Any]):
    """Returns the catalog's own credit and faculty distributions, for drawing hard negatives.

    Distractors are sampled from these rather than invented (the previous generator used
    `true_credits + 50`, which any 'implausibly large number is false' prior classifies correctly
    without consulting the graph at all).
    """
    credits = collections.Counter(r["credits"] for r in graph.values() if r.get("credits", 0) > 0)
    schools = collections.Counter(r["school"] for r in graph.values() if r.get("school"))
    return credits, schools


def weighted_choice_excluding(rng: random.Random, counter: collections.Counter, exclude) -> Any:
    population = [value for value in counter if value != exclude]
    weights = [counter[value] for value in population]
    return rng.choices(population, weights=weights, k=1)[0]


def absent_module_codes(rng: random.Random, graph: Dict[str, Any], n: int) -> List[str]:
    """Mints module codes that look like NUS codes but name nothing in the catalog.

    Two requirements pull against each other. A code that is obviously synthetic ("NUS90000")
    turns the Not-in-KG class into a string-pattern test. A code one digit off a real module
    ("CS2041" against "CS2040") is instead a test of the entity linker's rejection threshold, and
    at the default threshold the bi-encoder snaps it onto its neighbour. These codes use real
    department prefixes but differ from every same-prefix real code in at least two digit
    positions, so they read as plausible without sitting inside the linker's noise band.
    """
    by_prefix = collections.defaultdict(list)
    for code in graph:
        match = CODE_PARTS.match(code)
        if match and len(match.group(2)) == 4:
            by_prefix[match.group(1)].append(match.group(2))
    prefixes = sorted(p for p, digits in by_prefix.items() if len(digits) >= 5)

    minted, seen = [], set()
    attempts = 0
    while len(minted) < n and attempts < n * 400:
        attempts += 1
        prefix = rng.choice(prefixes)
        digits = "".join(str(rng.randint(0, 9)) for _ in range(4))
        candidate = prefix + digits
        if candidate in graph or candidate in seen:
            continue
        if any(sum(a != b for a, b in zip(digits, real)) < 2 for real in by_prefix[prefix]):
            continue
        seen.add(candidate)
        minted.append(candidate)
    if len(minted) < n:
        raise RuntimeError(f"Could only mint {len(minted)} of {n} absent module codes.")
    return minted


def _record(item_id, text, gold, reasoning_type, asserted, context):
    return {
        "id": item_id,
        "text": text,
        "gold_label": gold,
        "reasoning_type": reasoning_type,
        # `triples` is the KG evidence for the subject and is what the context_llm baseline is
        # shown. `asserted_triples` is what the sentence states. They differ on every Contradicted
        # row; collapsing them would hand the context baseline the answer.
        "triples": context,
        "asserted_triples": asserted,
    }


def _context_for(graph: Dict[str, Any], code: str) -> List[List[str]]:
    record = graph.get(code)
    if not record:
        return []
    context = []
    if record.get("credits") is not None:
        context.append([code, "hasCreditValue", str(record["credits"])])
    if record.get("school"):
        context.append([code, "partOfSchool", record["school"]])
    for prerequisite in record.get("prerequisites", []):
        context.append([code, "requiresPrerequisite", prerequisite["course_id"]])
    return context


def build(graph: Dict[str, Any], limit: int, seed: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    credit_dist, school_dist = value_distributions(graph)

    # Pools of modules that can carry each item type, sampled without replacement so no module
    # appears twice in the benchmark.
    with_credits = [c for c, r in graph.items() if r.get("credits", 0) > 0]
    with_school = [c for c, r in graph.items() if r.get("school")]
    without_prerequisites = [c for c, r in graph.items() if not r.get("prerequisites")]
    with_both = [c for c in with_credits if graph[c].get("school")]

    # A prerequisite rule may name a module the catalog no longer carries (retired codes, codes
    # from other institutions). Such an item is unverifiable by construction: the object cannot
    # be linked, so the row reports Not-in-KG however the verifier behaves. Restrict the pools to
    # prerequisites the graph actually holds, and keep the resolvable/unresolvable split out of
    # the benchmark rather than scoring it as a reasoning failure.
    resolvable_prerequisites = {
        code: [p["course_id"] for p in record["prerequisites"] if p["course_id"] in graph]
        for code, record in graph.items() if record.get("prerequisites")
    }
    with_prerequisites = [c for c, p in resolvable_prerequisites.items() if p]
    chains = [
        (code, intermediate)
        for code in with_prerequisites
        for intermediate in resolvable_prerequisites[code]
        if resolvable_prerequisites.get(intermediate)
    ]
    for pool in (with_credits, with_school, with_prerequisites, without_prerequisites, with_both):
        rng.shuffle(pool)
    rng.shuffle(chains)

    used = set()

    def take(pool):
        while pool:
            code = pool.pop()
            if code not in used:
                used.add(code)
                return code
        raise RuntimeError("Module pool exhausted; lower --limit.")

    counts = {
        label: {
            item_type: max(1, round(limit * LABEL_SHARES[label] * share))
            for item_type, share in types.items()
        }
        for label, types in TYPE_SHARES.items()
    }

    records: List[Dict[str, Any]] = []
    absent_needed = sum(counts["Not-in-KG"].values())
    absent_codes = absent_module_codes(rng, graph, absent_needed)

    def emit(text, gold, reasoning_type, asserted, context):
        records.append(_record(f"nus-{len(records) + 1:04d}", text, gold, reasoning_type,
                               asserted, context))

    for _ in range(counts["Supported"]["credit-one-hop"]):
        code = take(with_credits)
        record = graph[code]
        text = rng.choice(CREDIT_TEMPLATES).format(code=code, title=record["title"],
                                                   credits=record["credits"])
        emit(text, "Supported", "credit-one-hop",
             [[code, "hasCreditValue", str(record["credits"])]], _context_for(graph, code))

    for _ in range(counts["Supported"]["school-one-hop"]):
        code = take(with_school)
        record = graph[code]
        text = rng.choice(SCHOOL_TEMPLATES).format(code=code, title=record["title"],
                                                   school=record["school"])
        emit(text, "Supported", "school-one-hop",
             [[code, "partOfSchool", record["school"]]], _context_for(graph, code))

    for _ in range(counts["Supported"]["prerequisite-one-hop"]):
        code = take(with_prerequisites)
        record = graph[code]
        prerequisite = rng.choice(resolvable_prerequisites[code])
        text = rng.choice(PREREQUISITE_TEMPLATES).format(code=code, title=record["title"],
                                                         prerequisite=prerequisite)
        emit(text, "Supported", "prerequisite-one-hop",
             [[code, "requiresPrerequisite", prerequisite]], _context_for(graph, code))

    for _ in range(counts["Supported"]["prerequisite-negation"]):
        code = take(without_prerequisites)
        record = graph[code]
        text = rng.choice(NO_PREREQUISITE_TEMPLATES).format(code=code, title=record["title"])
        emit(text, "Supported", "prerequisite-negation",
             [[code, "requiresPrerequisite", "none"]], _context_for(graph, code))

    for _ in range(counts["Supported"]["prerequisite-multi-hop"]):
        while chains:
            code, intermediate = chains.pop()
            if code not in used:
                used.add(code)
                break
        else:
            break
        target = rng.choice(resolvable_prerequisites[intermediate])
        text = rng.choice(MULTI_HOP_TEMPLATES).format(code=code, target=target)
        emit(text, "Supported", "prerequisite-multi-hop",
             [[code, "requiresPrerequisite", target]],
             _context_for(graph, code) + _context_for(graph, intermediate))

    for _ in range(counts["Supported"]["conjunction"]):
        code = take(with_both)
        record = graph[code]
        text = rng.choice(CONJUNCTION_TEMPLATES).format(code=code, title=record["title"],
                                                        credits=record["credits"],
                                                        school=record["school"])
        emit(text, "Supported", "conjunction",
             [[code, "hasCreditValue", str(record["credits"])],
              [code, "partOfSchool", record["school"]]], _context_for(graph, code))

    for _ in range(counts["Contradicted"]["credit-one-hop"]):
        code = take(with_credits)
        record = graph[code]
        wrong = weighted_choice_excluding(rng, credit_dist, record["credits"])
        text = rng.choice(CREDIT_TEMPLATES).format(code=code, title=record["title"], credits=wrong)
        emit(text, "Contradicted", "credit-one-hop",
             [[code, "hasCreditValue", str(wrong)]], _context_for(graph, code))

    for _ in range(counts["Contradicted"]["school-one-hop"]):
        code = take(with_school)
        record = graph[code]
        wrong = weighted_choice_excluding(rng, school_dist, record["school"])
        text = rng.choice(SCHOOL_TEMPLATES).format(code=code, title=record["title"], school=wrong)
        emit(text, "Contradicted", "school-one-hop",
             [[code, "partOfSchool", wrong]], _context_for(graph, code))

    for _ in range(counts["Contradicted"]["prerequisite-negation"]):
        code = take(with_prerequisites)
        record = graph[code]
        text = rng.choice(NO_PREREQUISITE_TEMPLATES).format(code=code, title=record["title"])
        emit(text, "Contradicted", "prerequisite-negation",
             [[code, "requiresPrerequisite", "none"]], _context_for(graph, code))

    for _ in range(counts["Contradicted"]["conjunction"]):
        code = take(with_both)
        record = graph[code]
        wrong = weighted_choice_excluding(rng, credit_dist, record["credits"])
        text = rng.choice(CONJUNCTION_TEMPLATES).format(code=code, title=record["title"],
                                                        credits=wrong, school=record["school"])
        emit(text, "Contradicted", "conjunction",
             [[code, "hasCreditValue", str(wrong)],
              [code, "partOfSchool", record["school"]]], _context_for(graph, code))

    absent = iter(absent_codes)
    for _ in range(counts["Not-in-KG"]["absent-module-credit"]):
        code = next(absent)
        credits = weighted_choice_excluding(rng, credit_dist, None)
        text = f"Module {code} is worth {credits} Modular Credits."
        emit(text, "Not-in-KG", "absent-module-credit",
             [[code, "hasCreditValue", str(credits)]], [])

    for _ in range(counts["Not-in-KG"]["absent-module-school"]):
        code = next(absent)
        school = weighted_choice_excluding(rng, school_dist, None)
        text = f"Module {code} is offered by {school}."
        emit(text, "Not-in-KG", "absent-module-school", [[code, "partOfSchool", school]], [])

    for _ in range(counts["Not-in-KG"]["absent-module-prerequisite"]):
        code = next(absent)
        prerequisite = rng.choice(with_prerequisites or list(graph))
        text = f"Module {code} requires {prerequisite} as a prerequisite."
        emit(text, "Not-in-KG", "absent-module-prerequisite",
             [[code, "requiresPrerequisite", prerequisite]], [])

    rng.shuffle(records)
    for position, record in enumerate(records, start=1):
        record["id"] = f"nus-{position:04d}"
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", default="data/nusmods_graph.json")
    parser.add_argument("--out", default="data/nusmods_test.jsonl")
    parser.add_argument("--limit", type=int, default=500, help="Approximate number of items.")
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()

    graph = load_graph(args.graph)
    records = build(graph, args.limit, args.seed)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")

    labels = collections.Counter(r["gold_label"] for r in records)
    types = collections.Counter(r["reasoning_type"] for r in records)
    floor = max(labels.values()) / len(records)
    logger.info(f"Wrote {len(records)} items to {args.out}")
    logger.info(f"Labels: {dict(labels)}   majority-class floor: {floor:.2%}")
    logger.info(f"Reasoning types: {dict(sorted(types.items()))}")


if __name__ == "__main__":
    main()
