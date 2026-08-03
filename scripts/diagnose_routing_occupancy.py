"""E2 non-vacuity gate: is the world-assumption routing signal informative at all?

`VerificationPipeline._route` dispatches CWA vs OWA by comparing `KGStore.estimate_relation_occupancy(relation)`
against `cwa_threshold`. That comparison only carries information if occupancy actually *varies*
across relations. If every relation scores 0.0 or 1.0, then:

  * `routing_mode=dynamic` is indistinguishable from `fixed_cwa` for every mapped relation, and
  * sweeping `cwa_threshold` over (0.0, 1.0) cannot change a single verdict — the sweep is a flat line.

Run this before spending API budget on the E2 ablation. It is deterministic, LLM-free, and takes
seconds. Exit code 1 means the ablation as configured would measure nothing.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\diagnose_routing_occupancy.py
    & .venv\\Scripts\\python.exe scripts\\diagnose_routing_occupancy.py --json output/diagnostics/routing_occupancy.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.append(os.getcwd())

from kg_store import get_kg_store

# (graph path, relations to probe). The RMIT relations are the keys of the `field_map` inside
# estimate_relation_occupancy plus one deliberately unmapped relation, so the report shows both
# the mapped and the fall-through behaviour.
GRAPHS = {
    "rmit": (
        "data/rmit_graph.json",
        [
            "requiresPrerequisite",
            "hasCreditValue",
            "partOfSchool",
            "taughtBy",
            "coordinator",
            "email",
            "offeredInTerm",
        ],
    ),
    "catalog2": (
        "data/catalog2_graph.json",
        ["requiresPrerequisite", "hasCreditValue", "taught_by", "offered_terms", "name"],
    ),
    "codex": ("data/codex_graph.json", None),
    "metaqa": ("data/metaqa_graph.json", None),
    # NUSMods probes the three ontology relations its benchmark uses plus the three extra fields
    # the graph carries, so the report shows the spread the routing threshold would see.
    "nusmods": (
        "data/nusmods_graph.json",
        [
            "hasCreditValue",
            "partOfSchool",
            "requiresPrerequisite",
            "department",
            "preclusions",
            "semesters",
            "offeredInTerm",
        ],
    ),
}

SWEEP = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]


def validate_output_path(output_path):
    """Reject an output path that would overwrite any graph inspected by this diagnostic."""
    if not output_path:
        return
    resolved_output = Path(output_path).resolve()
    graph_paths = {Path(path).resolve() for path, _relations in GRAPHS.values()}
    if resolved_output in graph_paths:
        raise ValueError(
            f"Refusing to overwrite configured graph with diagnostic output: {resolved_output}"
        )


def discover_relations(store, limit=25):
    """Relations for graphs with no fixed ontology: the field names actually present."""
    seen = {}
    for record in store.courses.values():
        if not isinstance(record, dict):
            continue
        for field in record:
            seen[field] = seen.get(field, 0) + 1
    ordered = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    return [field for field, _ in ordered[:limit]]


def probe(name, path, relations):
    if not os.path.exists(path):
        return {"graph": name, "path": path, "status": "missing"}

    store = get_kg_store(path)
    if relations is None:
        relations = discover_relations(store)

    scores = {relation: store.estimate_relation_occupancy(relation) for relation in relations}
    interior = {r: s for r, s in scores.items() if 0.0 < s < 1.0}

    # A threshold only matters if some relation's routing flips as it moves.
    routes = {
        tau: {r: ("closed" if s >= tau else "open") for r, s in scores.items()}
        for tau in SWEEP
    }
    distinct_routings = {json.dumps(r, sort_keys=True) for r in routes.values()}

    return {
        "graph": name,
        "path": path,
        "status": "ok",
        "n_entities": len(store.courses),
        "occupancy": scores,
        "n_relations": len(scores),
        "n_saturated": sum(1 for s in scores.values() if s in (0.0, 1.0)),
        "n_interior": len(interior),
        "interior_relations": interior,
        "n_distinct_routings_over_sweep": len(distinct_routings),
        "threshold_is_informative": len(distinct_routings) > 1,
    }


def main():
    parser = argparse.ArgumentParser(description="E2 routing-signal non-vacuity gate")
    parser.add_argument("--json", dest="json_path", default=None, help="Write the report as JSON")
    parser.add_argument("--require", nargs="*", default=["rmit"],
                        help="Graphs that must carry an informative signal for the gate to pass.")
    args = parser.parse_args()
    validate_output_path(args.json_path)

    reports = [probe(name, path, relations) for name, (path, relations) in GRAPHS.items()]

    print("=" * 78)
    print("E2 ROUTING-SIGNAL NON-VACUITY GATE")
    print("=" * 78)
    for report in reports:
        if report["status"] == "missing":
            print(f"\n{report['graph']}: graph not found at {report['path']} — skipped")
            continue
        print(f"\n{report['graph']}  ({report['n_entities']} entities, {report['path']})")
        for relation, score in sorted(report["occupancy"].items(), key=lambda kv: (-kv[1], kv[0])):
            marker = "   " if 0.0 < score < 1.0 else " ! "
            print(f"  {marker}{relation:<32} {score:.4f}")
        print(f"  relations: {report['n_relations']}   saturated at 0.0/1.0: {report['n_saturated']}"
              f"   interior: {report['n_interior']}")
        print(f"  distinct routings across tau in {SWEEP}: {report['n_distinct_routings_over_sweep']}")
        if not report["threshold_is_informative"]:
            print("  VERDICT: cwa_threshold changes no routing decision on this graph. "
                  "dynamic == fixed_cwa for mapped relations; a tau sweep here is a flat line.")
        else:
            print("  VERDICT: threshold is informative — the sweep can change routing.")

    if args.json_path:
        os.makedirs(os.path.dirname(args.json_path) or ".", exist_ok=True)
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump({"sweep": SWEEP, "reports": reports}, handle, indent=2)
        print(f"\nWrote {args.json_path}")

    required = [r for r in reports if r["graph"] in args.require and r["status"] == "ok"]
    vacuous = [r["graph"] for r in required if not r["threshold_is_informative"]]
    print("\n" + "=" * 78)
    if vacuous:
        print(f"GATE FAILED for {', '.join(vacuous)}: the E2 ablation would measure nothing.")
        print("Fix the occupancy estimator (or run the ablation on a graph with interior scores)")
        print("before spending API budget on the sweep.")
        print("=" * 78)
        return 1
    print("GATE PASSED: the routing signal varies on every required graph.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
