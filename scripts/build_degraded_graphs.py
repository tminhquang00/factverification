"""Build reproducible incomplete NUSMods graph versions and deletion logs.

Random deletion samples individual relation facts. Clustered deletion retains or removes whole
department groups, modelling a failed departmental migration. Every output graph has a companion
completeness declaration: a relation that was deliberately degraded is declared incomplete even
when its observed occupancy remains high.
"""

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path


RELATION_FIELDS = {
    "hasCreditValue": "credits",
    "partOfSchool": "school",
    "requiresPrerequisite": "prerequisites",
    "preclusions": "preclusions",
    "offeredInTerm": "semesters",
}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_relation_facts(graph, relation):
    field = RELATION_FIELDS[relation]
    facts = []
    for subject, record in sorted(graph.items()):
        value = record.get(field)
        if isinstance(value, list):
            for item in value:
                obj = item.get("course_id") if isinstance(item, dict) else item
                if obj not in (None, ""):
                    facts.append((subject, relation, str(obj)))
        elif value not in (None, "", "Unknown"):
            facts.append((subject, relation, str(value)))
    return facts


def select_retained_facts(graph, facts, retention, mode, rng):
    target = round(len(facts) * retention)
    if target >= len(facts):
        return set(facts)
    if target <= 0:
        return set()
    if mode == "random":
        return set(rng.sample(facts, target))

    groups = {}
    for fact in facts:
        subject = fact[0]
        department = graph[subject].get("department") or graph[subject].get("school") or "<unknown>"
        groups.setdefault(str(department), []).append(fact)
    names = sorted(groups)
    rng.shuffle(names)
    retained = []
    for name in names:
        candidate = retained + groups[name]
        if len(candidate) <= target:
            retained = candidate
            continue
        if abs(len(candidate) - target) < abs(len(retained) - target):
            retained = candidate
        break
    return set(retained)


def degrade_graph(graph, retention, mode, seed, relations=None):
    """Returns ``(degraded_graph, deleted_facts, statistics)`` without mutating ``graph``."""
    if not 0.0 <= retention <= 1.0:
        raise ValueError("retention must be between 0 and 1")
    if mode not in {"random", "clustered"}:
        raise ValueError("mode must be random or clustered")
    relations = relations or list(RELATION_FIELDS)
    degraded = copy.deepcopy(graph)
    deleted = []
    stats = {}

    for relation_index, relation in enumerate(relations):
        if relation not in RELATION_FIELDS:
            raise ValueError(f"Unsupported degradable relation: {relation}")
        facts = iter_relation_facts(graph, relation)
        rng = random.Random(seed + relation_index * 100003)
        retained = select_retained_facts(graph, facts, retention, mode, rng)
        removed = [fact for fact in facts if fact not in retained]
        deleted.extend(removed)

        field = RELATION_FIELDS[relation]
        removed_by_subject = {}
        for subject, _relation, obj in removed:
            removed_by_subject.setdefault(subject, set()).add(obj)
        for subject, removed_values in removed_by_subject.items():
            original_value = graph[subject].get(field)
            if isinstance(original_value, list):
                kept_values = []
                for item in original_value:
                    obj = item.get("course_id") if isinstance(item, dict) else item
                    if str(obj) not in removed_values:
                        kept_values.append(item)
                if kept_values:
                    degraded[subject][field] = kept_values
                else:
                    # Empty in the source means a declared empty set. Empty after deletion means
                    # the set is unknown, so remove the field instead of fabricating "none".
                    degraded[subject].pop(field, None)
            else:
                degraded[subject].pop(field, None)

        stats[relation] = {
            "original_facts": len(facts),
            "retained_facts": len(retained),
            "deleted_facts": len(removed),
            "realized_retention": len(retained) / len(facts) if facts else 1.0,
        }
    return degraded, deleted, stats


def degraded_declaration(base_declaration, retention, relations):
    declaration = copy.deepcopy(base_declaration)
    declaration["degradation_retention"] = retention
    if retention < 1.0:
        for relation in relations:
            declaration.setdefault("relations", {})[relation] = "incomplete"
    return declaration


def write_condition(
    graph, base_declaration, output_dir, retention, mode, seed, relations,
    dataset_name="nusmods",
):
    degraded, deleted, stats = degrade_graph(graph, retention, mode, seed, relations)
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / f"{dataset_name}_graph.json"
    log_path = output_dir / "deletion_log.jsonl"
    declaration_path = output_dir / "completeness.json"
    manifest_path = output_dir / "manifest.json"

    graph_path.write_text(json.dumps(degraded, indent=2), encoding="utf-8")
    with log_path.open("w", encoding="utf-8") as handle:
        for subject, relation, obj in deleted:
            handle.write(json.dumps({"subject": subject, "relation": relation, "object": obj}) + "\n")
    declaration_path.write_text(
        json.dumps(degraded_declaration(base_declaration, retention, relations), indent=2),
        encoding="utf-8",
    )
    manifest = {
        "mode": mode,
        "requested_retention": retention,
        "seed": seed,
        "relations": relations,
        "statistics": stats,
        "graph_sha256": file_sha256(graph_path),
        "deletion_log_sha256": file_sha256(log_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/nusmods_graph.json")
    parser.add_argument("--declaration", default="data/completeness_declarations/nusmods.json")
    parser.add_argument("--outdir", default="output/experiments/nusmods_degradation")
    parser.add_argument("--retention", type=float, nargs="+", default=[1.0, 0.8, 0.5, 0.2])
    parser.add_argument("--modes", nargs="+", choices=["random", "clustered"], default=["random", "clustered"])
    parser.add_argument("--relations", nargs="+", choices=sorted(RELATION_FIELDS), default=list(RELATION_FIELDS))
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--dataset_name", default="nusmods")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    declaration = json.loads(Path(args.declaration).read_text(encoding="utf-8"))
    root = Path(args.outdir)
    summary = {}
    for mode in args.modes:
        for retention in args.retention:
            condition = f"{mode}__retention_{int(round(retention * 100)):03d}"
            summary[condition] = write_condition(
                graph, declaration, root / condition, retention, mode, args.seed, args.relations,
                dataset_name=args.dataset_name,
            )
            summary[condition]["source_graph_sha256"] = file_sha256(args.graph)
            summary[condition]["base_declaration_sha256"] = file_sha256(args.declaration)
            summary[condition]["script_sha256"] = file_sha256(__file__)
            (root / condition / "manifest.json").write_text(
                json.dumps(summary[condition], indent=2), encoding="utf-8"
            )
            print(f"wrote {condition}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
