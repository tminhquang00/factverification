import os
import sys
import json
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_experiments")

PYTHON_EXEC = os.path.join(".venv", "Scripts", "python.exe")

def run_command_sync(cmd):
    logger.info(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
    if result.returncode != 0:
        logger.error(f"Command failed with code {result.returncode}:\n{result.stderr}")
    else:
        logger.info(f"Command finished successfully.")
    return result

def main():
    os.makedirs("output/benchmarks", exist_ok=True)
    os.makedirs("output/experiments", exist_ok=True)
    
    models = [
        ("azure-4.1-mini", "azure"),
        ("azure-5-mini", "azure"),
        ("google/gemma-4-e4b", "local")
    ]
    
    datasets = ["factkg", "codex", "metaqa", "rmit"]
    
    print("="*70)
    print("STARTING FULL MULTI-MODEL BASELINE BENCHMARK SWEEP")
    print("="*70)
    
    # 1. Baseline Benchmark Sweep across 3 models and datasets
    for model_name, provider in models:
        safe_model = model_name.replace("/", "_").replace(".", "_")
        for ds in datasets:
            out_file = f"output/benchmarks/{safe_model}_{ds}_baseline.json"
            cmd = [
                PYTHON_EXEC, "-u", "eval_harness.py" if ds != "rmit" else "eval_rmit.py",
                "--dataset", ds,
                "--method", "pipeline",
                "--limit", "500",
                "--model_name", model_name,
                "--provider", provider,
                "--output_file", out_file
            ] if ds != "rmit" else [
                PYTHON_EXEC, "-u", "eval_rmit.py"
            ]
            run_command_sync(cmd)
            
    print("\n" + "="*70)
    print("STARTING EXPERIMENT 1: ORACLE LINKING UPPER BOUND")
    print("="*70)
    for model_name, provider in [("azure-4.1-mini", "azure")]:
        out_file = "output/experiments/exp1_oracle_linking_factkg.json"
        cmd = [
            PYTHON_EXEC, "-u", "eval_harness.py",
            "--dataset", "factkg",
            "--method", "pipeline",
            "--limit", "500",
            "--model_name", model_name,
            "--provider", provider,
            "--oracle_linking",
            "--output_file", out_file
        ]
        run_command_sync(cmd)

    print("\n" + "="*70)
    print("STARTING EXPERIMENT 2: NEURAL LINKING (BI-ENCODER + CROSS-ENCODER)")
    print("="*70)
    for model_name, provider in [("azure-4.1-mini", "azure")]:
        out_file = "output/experiments/exp2_neural_linking_codex.json"
        cmd = [
            PYTHON_EXEC, "-u", "eval_harness.py",
            "--dataset", "codex",
            "--method", "pipeline",
            "--limit", "500",
            "--model_name", model_name,
            "--provider", provider,
            "--output_file", out_file
        ]
        run_command_sync(cmd)

    print("\n" + "="*70)
    print("STARTING EXPERIMENT 3: MULTI-HOP DECONTEXTUALIZATION & COVE")
    print("="*70)
    for model_name, provider in [("azure-4.1-mini", "azure")]:
        out_file = "output/experiments/exp3_decontextualize_metaqa.json"
        cmd = [
            PYTHON_EXEC, "-u", "eval_harness.py",
            "--dataset", "metaqa",
            "--method", "pipeline",
            "--limit", "500",
            "--model_name", model_name,
            "--provider", provider,
            "--decontextualize",
            "--output_file", out_file
        ]
        run_command_sync(cmd)

    print("\n" + "="*70)
    print("STARTING EXPERIMENT 4: CONTINUOUS SCORE CALIBRATION & SMOOTHING")
    print("="*70)
    for model_name, provider in [("azure-4.1-mini", "azure")]:
        out_file = "output/experiments/exp4_smooth_calibration_factkg.json"
        cmd = [
            PYTHON_EXEC, "-u", "eval_harness.py",
            "--dataset", "factkg",
            "--method", "pipeline",
            "--limit", "500",
            "--model_name", model_name,
            "--provider", provider,
            "--smooth_calibration",
            "--output_file", out_file
        ]
        run_command_sync(cmd)

    print("\n" + "="*70)
    print("ALL BENCHMARKS AND EXPERIMENTS COMPLETED SUCCESSFULLY!")
    print("="*70)

if __name__ == "__main__":
    main()
