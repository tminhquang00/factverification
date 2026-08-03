"""Compile the raw NUSMods API dumps into a pipeline-native knowledge graph.

Input
-----
`data/nusmods/<AY>_moduleInformation.json` — one file per academic year, as downloaded by
`scripts/download_nusmods.py` from the NUSMods v2 API.

Output
------
* `data/nusmods_graph.json` — the graph `KGStore` loads.
* `data/nusmods_graph.ttl` — the same graph in RDF Turtle, for external inspection.
* `data/completeness_profiles/nusmods.json` — measured per-relation occupancy.

Schema
------
The graph is emitted in the field names `KGStore` and `VerificationPipeline` already dispatch on,
so NUSMods runs through the same stage-4 branches RMIT does rather than through the open-domain
relation-normalization fallback:

    "CS2040": {
        "course_id":   "CS2040",
        "title":       "Data Structures and Algorithms",
        "credits":     4,                                  -> hasCreditValue
        "school":      "Computing",                        -> partOfSchool   (NUSMods `faculty`)
        "prerequisites": [{"course_id": "CS1010", ...}],    -> requiresPrerequisite
        "department":  "Computer Science",
        ...
    }

Two conventions matter for the validity of anything measured on this graph:

1. **Catalog-empty sets are explicit.** The module record is treated as authoritative for catalog
   prerequisites, preclusions, and offered semesters. A missing source field compiles to an empty
   list, distinguishing "the catalog declares none" from a relation field removed by a degradation
   experiment. Occupancy still counts only non-empty values; declared completeness is independent.

2. **`prerequisites` holds every module named in the prerequisite rule, alternatives included.**
   The API exposes the rule as free text ("must have completed 1 of CS1010/CS1010E/CS1101S"), not
   as a tree, so the list is the set of modules the rule mentions and not a conjunction. Claims
   built on it are therefore "X is named as a prerequisite option of Y", which is what
   `data/rmit_graph.json` also encodes.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\parse_nusmods.py
"""

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("parse_nusmods")

MODULE_CODE_REGEX = re.compile(r"\b([A-Z]{2,4}\d{4}[A-Z]*)\b")

# Relations the graph supports, mapped to the field each one reads. Kept next to the writer so the
# profile and the graph cannot drift apart.
RELATION_FIELDS = {
    "hasCreditValue": "credits",
    "partOfSchool": "school",
    "requiresPrerequisite": "prerequisites",
    "department": "department",
    "preclusions": "preclusions",
    "corequisites": "corequisites",
    "semesters": "semesters",
    "grading_basis": "grading_basis",
}


def extract_module_codes(text: str, exclude: str = None) -> List[str]:
    """Returns the module codes named in a free-text requirement rule, in order, deduplicated."""
    if not text:
        return []
    seen, codes = set(), []
    for code in MODULE_CODE_REGEX.findall(text):
        if code in seen or code == exclude:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _credits(raw) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _clean(value) -> str:
    """Normalizes a string field, mapping the catalog's placeholders onto absence."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"unknown", "n/a", "nil", "-"}:
        return None
    return text


def parse_all_nusmods_years(directory: str = "data/nusmods") -> Dict[str, Any]:
    """Builds the union of every academic year, keeping each module's most recent record."""
    filenames = sorted(f for f in os.listdir(directory) if f.endswith("moduleInformation.json"))
    if not filenames:
        raise FileNotFoundError(
            f"No *_moduleInformation.json under {directory}. Run scripts/download_nusmods.py first."
        )
    logger.info(f"Parsing {len(filenames)} academic years from {directory}: {filenames}")

    graph: Dict[str, Any] = {}
    for filename in filenames:
        academic_year = filename.split("_")[0]
        path = os.path.join(directory, filename)
        with open(path, "r", encoding="utf-8") as handle:
            modules = json.load(handle)

        kept = 0
        for item in modules:
            code = _clean(item.get("moduleCode"))
            if not code:
                continue
            # Files are read oldest-first, so a later year overwrites an earlier one. The guard
            # keeps that explicit rather than relying on iteration order alone.
            if code in graph and academic_year < graph[code]["academic_year"]:
                continue

            record: Dict[str, Any] = {
                "course_id": code,
                "title": _clean(item.get("title")) or code,
                "academic_year": academic_year,
            }

            credits = _credits(item.get("moduleCredit"))
            if credits is not None:
                record["credits"] = credits

            # NUSMods `faculty` is the awarding unit; it occupies the same slot in the ontology
            # that `school` does on RMIT, which is the field stage 4's partOfSchool branch reads.
            for field, source in (("school", "faculty"), ("department", "department"),
                                  ("description", "description")):
                value = _clean(item.get(source))
                if value:
                    record[field] = value

            grading = _clean(item.get("gradingBasisDescription"))
            if grading:
                record["grading_basis"] = grading

            prerequisite_text = _clean(item.get("prerequisite"))
            prerequisites = extract_module_codes(prerequisite_text, exclude=code)
            record["prerequisites"] = []
            if prerequisites:
                record["prerequisite_text"] = prerequisite_text
                # Stage 4 reads prerequisites through KGStore.get_prerequisites, which expects
                # {"course_id": ...} entries. Titles are backfilled once the union is complete.
                record["prerequisites"] = [{"course_id": p, "title": p} for p in prerequisites]

            preclusion_text = _clean(item.get("preclusion"))
            preclusions = extract_module_codes(preclusion_text, exclude=code)
            record["preclusions"] = preclusions
            if preclusions:
                record["preclusion_text"] = preclusion_text

            corequisites = extract_module_codes(_clean(item.get("corequisite")), exclude=code)
            if corequisites:
                record["corequisites"] = corequisites

            semesters = sorted({
                str(entry["semester"])
                for entry in item.get("semesterData") or []
                if isinstance(entry, dict) and entry.get("semester") is not None
            })
            record["semesters"] = semesters

            graph[code] = record
            kept += 1

        logger.info(f"  {academic_year}: {len(modules)} modules read, {kept} records written")

    _backfill_prerequisite_titles(graph)
    logger.info(f"Graph holds {len(graph)} unique modules across all years.")
    return graph


def _backfill_prerequisite_titles(graph: Dict[str, Any]):
    """Fills prerequisite titles from the graph once every year has been merged."""
    for record in graph.values():
        for prerequisite in record.get("prerequisites", []):
            target = graph.get(prerequisite["course_id"])
            if target:
                prerequisite["title"] = target["title"]


def build_completeness_profile(graph: Dict[str, Any], output_path: str):
    """Writes measured per-relation occupancy over the compiled graph.

    The numbers are the fraction of module records carrying a populated value, computed the same
    way `KGStore.estimate_relation_occupancy` computes it at verification time. Nothing in the
    pipeline reads this file — stage-4 routing recomputes occupancy live from the loaded graph —
    so it is a reporting artifact, not a control input.
    """
    total = len(graph)
    if total == 0:
        raise ValueError("Refusing to write a completeness profile for an empty graph.")

    occupancy = {}
    for relation, field in RELATION_FIELDS.items():
        present = sum(1 for record in graph.values() if record.get(field) not in (None, "", [], {}))
        occupancy[relation] = round(present / total, 4)

    profile = {
        "dataset": "nusmods",
        "total_entities": total,
        "relation_field_map": RELATION_FIELDS,
        "relation_completeness": occupancy,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2)
    logger.info(f"Saved occupancy profile to {output_path}: {occupancy}")
    return occupancy


def _ttl_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def build_turtle_graph(graph: Dict[str, Any], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("@prefix nus: <http://nus.edu.sg/nusmods/> .\n")
        handle.write("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n")
        for code, record in graph.items():
            lines = [f'    nus:moduleCode "{_ttl_literal(code)}"',
                     f'    nus:title "{_ttl_literal(record["title"])}"']
            if "credits" in record:
                lines.append(f'    nus:hasCreditValue {record["credits"]}')
            if "school" in record:
                lines.append(f'    nus:partOfSchool "{_ttl_literal(record["school"])}"')
            if "department" in record:
                lines.append(f'    nus:department "{_ttl_literal(record["department"])}"')
            for prerequisite in record.get("prerequisites", []):
                lines.append(f'    nus:requiresPrerequisite nus:M{prerequisite["course_id"]}')
            for preclusion in record.get("preclusions", []):
                lines.append(f"    nus:preclusions nus:M{preclusion}")
            for semester in record.get("semesters", []):
                lines.append(f'    nus:semesters "{semester}"')
            handle.write(f"nus:M{code} a nus:Module ;\n" + " ;\n".join(lines) + " .\n\n")
    logger.info(f"Saved RDF Turtle graph to {output_path}")


def build_snapshot_manifest(input_dir: str, graph_path: str, output_path: str, fetch_date=None):
    """Records hashes for the exact raw snapshot inputs and compiled graph."""
    files = []
    for filename in sorted(os.listdir(input_dir)):
        if not filename.endswith(("moduleInformation.json", "moduleList.json")):
            continue
        path = os.path.join(input_dir, filename)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append({
            "path": path.replace("\\", "/"),
            "sha256": digest.hexdigest(),
            "size_bytes": os.path.getsize(path),
        })

    graph_digest = hashlib.sha256()
    with open(graph_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            graph_digest.update(chunk)
    observed_fetch_date = fetch_date or datetime.fromtimestamp(
        max(os.path.getmtime(item["path"]) for item in files), timezone.utc
    ).date().isoformat()
    manifest = {
        "dataset": "nusmods",
        "source": "NUSMods v2 API",
        "academic_years": sorted({item["path"].split("/")[-1].split("_")[0] for item in files}),
        "fetch_date": observed_fetch_date,
        "snapshot_id": f"nusmods-ay2020-2026-{graph_digest.hexdigest()[:12]}",
        "compiled_graph": graph_path.replace("\\", "/"),
        "compiled_graph_sha256": graph_digest.hexdigest(),
        "raw_files": files,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    logger.info("Saved snapshot manifest to %s", output_path)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input_dir", default="data/nusmods")
    parser.add_argument("--graph_out", default="data/nusmods_graph.json")
    parser.add_argument("--ttl_out", default="data/nusmods_graph.ttl")
    parser.add_argument("--profile_out", default="data/completeness_profiles/nusmods.json")
    parser.add_argument("--manifest_out", default="data/nusmods_snapshot.manifest.json")
    parser.add_argument("--fetch_date", default=None,
                        help="YYYY-MM-DD source fetch date. Defaults to the newest raw-file mtime.")
    args = parser.parse_args()

    graph = parse_all_nusmods_years(args.input_dir)

    os.makedirs(os.path.dirname(args.graph_out), exist_ok=True)
    with open(args.graph_out, "w", encoding="utf-8") as handle:
        json.dump(graph, handle, indent=2)
    logger.info(f"Saved JSON graph to {args.graph_out}")

    build_turtle_graph(graph, args.ttl_out)
    build_completeness_profile(graph, args.profile_out)
    build_snapshot_manifest(args.input_dir, args.graph_out, args.manifest_out, args.fetch_date)
    print("\nRun scripts/build_nusmods_benchmark.py next to regenerate data/nusmods_test.jsonl.")


if __name__ == "__main__":
    main()
