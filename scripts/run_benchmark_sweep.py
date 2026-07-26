"""Run the full benchmark sweep as parallel subprocesses and record a process manifest.

Each cell is a separate process so one crash cannot take down the sweep, and every cell's
stdout/stderr is captured to its own log. The manifest records exit codes, UTC timestamps, and
the exact argv used, so a run is reconstructable without consulting shell history.

Design note: FactKG and CoDEx are run under BOTH sampling modes. The previous study used prefix
sampling (`data[:limit]`), but `data/factkg_test.jsonl` is sorted into contiguous reasoning-type
blocks, so its first 500 rows cover 2 of 13 reasoning types with a majority floor of 64.6% against
the full set's 51.35%. Running both modes lets the report attribute a change to the code fix rather
than to the sample.

Usage
-----
    & .venv\\Scripts\\python.exe scripts\\run_benchmark_sweep.py --run_id rerun_20260726_fixed
"""

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable

ENGINES = [
    ("azure-4.1-mini", "azure"),
    ("google/gemma-4-e4b", "local"),
]


def slug(text: str) -> str:
    return text.replace("/", "_").replace(".", "_").replace("-", "_")


def build_cells(args, outdir: Path):
    cells = []
    for model, provider in ENGINES:
        tag = slug(model)

        cells.append({
            "name": f"rmit__{tag}",
            "dataset": "rmit",
            "model": model,
            "provider": provider,
            "sampling": "full",
            "argv": [
                PYTHON, "eval_rmit.py",
                "--limit", str(args.rmit_limit),
                "--provider", provider,
                "--model_name", model,
                "--max_workers", str(args.max_workers),
                "--seed", "42",
                "--output_file", str(outdir / f"rmit__{tag}.json"),
            ],
        })

        for dataset, limit in (("factkg", args.public_limit), ("codex", args.public_limit),
                               ("nusmods", args.public_limit)):
            for sampling in args.sampling:
                extra = []
                # CoDEx runs against the open-domain graph, where the entity-link threshold was
                # calibrated on a held-out split (scripts/sweep_entity_threshold.py). NUSMods runs
                # against an 11.6k-module catalog whose Not-in-KG rows name codes that do not
                # exist; at the 0.35 default the bi-encoder snaps them onto a real module, so the
                # threshold is selected by scripts/diagnose_nusmods_stage4.py.
                if dataset in ("codex", "nusmods"):
                    extra = ["--entity_link_threshold", str(args.entity_link_threshold)]
                cells.append({
                    "name": f"{dataset}__{tag}__{sampling}",
                    "dataset": dataset,
                    "model": model,
                    "provider": provider,
                    "sampling": sampling,
                    "argv": [
                        PYTHON, "eval_harness.py",
                        "--dataset", dataset,
                        "--method", "pipeline",
                        "--limit", str(limit),
                        "--provider", provider,
                        "--model_name", model,
                        "--max_workers", str(args.max_workers),
                        "--sample", sampling,
                        "--sample_seed", str(args.sample_seed),
                        *extra,
                        "--output_file", str(outdir / f"{dataset}__{tag}__{sampling}.json"),
                    ],
                })
    return cells


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--outdir", default="output/experiments")
    parser.add_argument("--rmit_limit", type=int, default=300)
    parser.add_argument("--public_limit", type=int, default=500)
    parser.add_argument("--max_workers", type=int, default=4)
    parser.add_argument("--sampling", nargs="+", default=["random", "prefix"], choices=["random", "prefix"])
    parser.add_argument("--sample_seed", type=int, default=20260725)
    parser.add_argument("--entity_link_threshold", type=float, default=0.95)
    parser.add_argument("--max_parallel", type=int, default=4)
    parser.add_argument("--skip_existing", action="store_true",
                        help="Skip cells whose result JSON already exists, so an interrupted sweep resumes.")
    args = parser.parse_args()

    outdir = Path(args.outdir) / args.run_id
    outdir.mkdir(parents=True, exist_ok=True)
    cells = build_cells(args, outdir)

    if args.skip_existing:
        remaining = []
        for cell in cells:
            result = outdir / f"{cell['name']}.json"
            if result.exists():
                print(f"  [skip] {cell['name']} (result already present)")
            else:
                remaining.append(cell)
        cells = remaining

    print(f"Sweep {args.run_id}: {len(cells)} cells to run -> {outdir}\n")

    manifest, running = [], []

    def launch(cell):
        log_path = outdir / f"{cell['name']}.log"
        handle = open(log_path, "w", encoding="utf-8")
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        proc = subprocess.Popen(cell["argv"], stdout=handle, stderr=subprocess.STDOUT, text=True)
        print(f"  [start] {cell['name']}")
        return {"cell": cell, "proc": proc, "handle": handle, "log": log_path, "started": started}

    pending = list(cells)
    while pending or running:
        while pending and len(running) < args.max_parallel:
            running.append(launch(pending.pop(0)))
        for job in list(running):
            if job["proc"].poll() is None:
                continue
            job["handle"].close()
            running.remove(job)
            finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
            code = job["proc"].returncode
            print(f"  [{'ok' if code == 0 else 'FAIL'}] {job['cell']['name']} (exit {code})")
            manifest.append({
                **{k: v for k, v in job["cell"].items() if k != "argv"},
                "argv": job["cell"]["argv"],
                "exit_code": code,
                "started_utc": job["started"],
                "finished_utc": finished,
                "log": str(job["log"]),
            })
        if running:
            time.sleep(2)

    manifest_path = outdir / "process_manifest.json"
    if manifest_path.exists():
        # Resumed sweep: keep entries for cells this invocation skipped.
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        fresh = {entry["name"] for entry in manifest}
        manifest = [entry for entry in previous if entry["name"] not in fresh] + manifest
    manifest.sort(key=lambda entry: entry["name"])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    failures = [entry["name"] for entry in manifest if entry["exit_code"] != 0]
    print(f"\nWrote {manifest_path}")
    print(f"Cells: {len(manifest)}   failures: {len(failures)}")
    for name in failures:
        print(f"  FAILED: {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
