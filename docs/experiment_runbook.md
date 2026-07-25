# Experiment Runbook: RMIT, FactKG, and CoDEx

This runbook describes how to run the current experiments from Windows PowerShell and where every result is saved.

Run all commands from the repository root:

```powershell
Set-Location C:\Users\Admin\Desktop\crawler
```

## 1. Result-Saving Rules

| Command | Saved automatically? | Output |
| --- | --- | --- |
| Unit tests | No | Terminal only |
| RMIT benchmark generator | Yes | `data/advising/rmit_prerequisite_completeness_v0.jsonl` and manifest |
| RMIT graph-destruction control | Yes | Row-level JSONL and summary JSON under `output/experiments/` |
| RMIT expert-audit generator/validator | Yes | CSV, manifest, and summary under `data/advising/` |
| `eval_rmit.py` | Yes | `output/rmit_evaluation_run.json` |
| `eval_harness.py` for FactKG/CoDEx | Only with `--output_file` | The path supplied to `--output_file` |

> [!IMPORTANT]
> If `--output_file` is omitted from a FactKG or CoDEx command, metrics are printed to the terminal but no result JSON is written.

The repository's `.gitignore` excludes `output/`. Experiment outputs remain on the local machine but do not normally appear in Git commits.

Saving a result does not automatically make it validated or citable. New runs remain local candidate artifacts until their protocol and consistency checks are recorded in `experiments/registry.json`.

## 2. Environment Setup

Install dependencies using the repository virtual environment:

```powershell
& .venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the regression suite before an experiment:

```powershell
& .venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected current result: 23 tests pass.

### Local LLM

Start an OpenAI-compatible local server such as LM Studio, load the model, and configure `.env`:

```ini
LLM_PROVIDER=local
LOCAL_LLM_API_BASE=http://localhost:1234/v1
LOCAL_LLM_MODEL_NAME=google/gemma-4-e4b
```

The model name must match the identifier exposed by the local server.

### Azure OpenAI

Configure `.env` without committing it:

```ini
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2025-03-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=azure-4.1-mini
```

RMIT deterministic completeness and graph-destruction experiments do not call an LLM. FactKG, CoDEx, and the legacy RMIT claim-level evaluation do.

## 3. Check Input Data

The current workspace contains:

| Dataset | File | Rows |
| --- | --- | ---: |
| RMIT claim benchmark | `data/rmit_test_set.jsonl` | 300 |
| RMIT completeness candidate | `data/advising/rmit_prerequisite_completeness_v0.jsonl` | 181 |
| FactKG | `data/factkg_test.jsonl` | 9,041 |
| CoDEx | `data/codex_test.jsonl` | 1,000 |

Recount the files locally:

```powershell
$paths = @(
    "data/rmit_test_set.jsonl",
    "data/advising/rmit_prerequisite_completeness_v0.jsonl",
    "data/factkg_test.jsonl",
    "data/codex_test.jsonl"
)

foreach ($path in $paths) {
    $count = (Get-Content $path | Where-Object { $_.Trim() }).Count
    Write-Host "$path`: $count"
}
```

## 4. RMIT Completeness Experiment

This is the primary new experiment track. It evaluates completeness of the course IDs listed in each course's prerequisite section. It does not yet model prerequisite `AND`/`OR` logic or student eligibility.

### Step 1: Generate the candidate benchmark

```powershell
& .venv\Scripts\python.exe scripts\generate_advising_benchmark.py
```

Saved outputs:

* `data/advising/rmit_prerequisite_completeness_v0.jsonl`: 181 row-level candidate responses.
* `data/advising/rmit_prerequisite_completeness_v0.manifest.json`: graph hash, split counts, condition counts, and status.

This command overwrites those two generated v0 files deterministically.

### Step 2: Generate the expert-audit packet

```powershell
& .venv\Scripts\python.exe scripts\generate_advisor_audit_packet.py
```

Saved outputs:

* `data/advising/rmit_prerequisite_expected_set_audit_v0.csv`
* `data/advising/rmit_prerequisite_expected_set_audit_v0.manifest.json`

> [!WARNING]
> Regenerating the packet overwrites reviewer entries in the CSV. Generate it before review, not after the reviewer starts editing it.

The reviewer follows [advisor_audit_protocol.md](advisor_audit_protocol.md). Test and calibration courses are reviewed first.

### Step 3: Validate the audit packet

```powershell
& .venv\Scripts\python.exe scripts\validate_advisor_audit.py
```

Saved output:

* `data/advising/rmit_prerequisite_expected_set_audit_v0.summary.json`

Before review, the expected status is `awaiting_review`. The packet is ready for a revised dataset only when the status becomes `ready_for_dataset_revision`.

Inspect the audit status:

```powershell
$audit = Get-Content data\advising\rmit_prerequisite_expected_set_audit_v0.summary.json -Raw | ConvertFrom-Json
$audit | Select-Object status, reviewed_courses, remaining_required_courses, validation_errors | Format-List
```

### Step 4: Run the paired graph-destruction control

Run the held-out test split with the default five permutation seeds:

```powershell
& .venv\Scripts\python.exe scripts\run_graph_destruction_control.py
```

Saved outputs:

* `output/experiments/e0_prerequisite_graph_destruction_v0.rows.jsonl`: one row per example, graph condition, and seed.
* `output/experiments/e0_prerequisite_graph_destruction_v0.summary.json`: aggregate metrics, graph hashes, artifact hashes, and subject-clustered intervals.

Inspect the condition table:

```powershell
$summary = Get-Content output\experiments\e0_prerequisite_graph_destruction_v0.summary.json -Raw | ConvertFrom-Json
$summary.condition_summaries |
    Select-Object condition, seed, n, accuracy, observed_accuracy_drop_vs_baseline, clustered_bootstrap_ci_95 |
    Format-Table -AutoSize
```

Run another split or seed set without replacing the default outputs:

```powershell
& .venv\Scripts\python.exe scripts\run_graph_destruction_control.py `
    --split development `
    --seeds 101 103 107 `
    --rows output\experiments\e0_prerequisite_graph_destruction_development.rows.jsonl `
    --summary output\experiments\e0_prerequisite_graph_destruction_development.summary.json
```

### Optional: Legacy RMIT claim-level evaluation

```powershell
& .venv\Scripts\python.exe eval_rmit.py
```

This always saves detailed predictions to:

* `output/rmit_evaluation_run.json`

This 300-row synthetic benchmark is useful as a decomposition and claim-verification component test. It is not an answer-completeness or advisor-audited benchmark and must not support the headline paper claim.

## 5. FactKG Experiments

FactKG is a binary `Supported`/`Contradicted` claim-verification benchmark. The harness maps uncertainty outcomes such as `Not-in-KG` to `Contradicted` for forced binary evaluation. It does not test set-valued answer completeness.

### FactKG smoke test

Use one worker first to simplify debugging and avoid unnecessary API concurrency:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset factkg `
    --method pipeline `
    --limit 20 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 1 `
    --output_file output\experiments\factkg_pipeline_smoke.json
```

Saved output:

* `output/experiments/factkg_pipeline_smoke.json`

### Fixed-size experiment

After the smoke test passes, run a preregistered sample size such as 500:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset factkg `
    --method pipeline `
    --limit 500 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 4 `
    --output_file output\experiments\factkg_pipeline_local_n500.json
```

Azure variant:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset factkg `
    --method pipeline `
    --limit 500 `
    --provider azure `
    --model_name azure-4.1-mini `
    --max_workers 4 `
    --output_file output\experiments\factkg_pipeline_azure_n500.json
```

### Baselines

Closed-book LLM:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset factkg `
    --method closed_book_llm `
    --limit 500 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 4 `
    --output_file output\experiments\factkg_closed_book_local_n500.json
```

Context LLM:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset factkg `
    --method context_llm `
    --limit 500 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 4 `
    --output_file output\experiments\factkg_context_llm_local_n500.json
```

The complete file has 9,041 rows. A full run can be requested with `--limit 9041`, but it is expensive and should only be run after freezing the model, prompt, code, and evaluation plan.

## 6. CoDEx Experiments

CoDEx uses the background graph in `data/codex_graph.json` and the tri-state labels in `data/codex_test.jsonl`. The current file has 1,000 rows. This remains a claim-level public benchmark, not a response-completeness benchmark.

### CoDEx smoke test

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset codex `
    --method pipeline `
    --limit 20 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 1 `
    --output_file output\experiments\codex_pipeline_smoke.json
```

### Fixed-size or full experiment

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset codex `
    --method pipeline `
    --limit 500 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 4 `
    --output_file output\experiments\codex_pipeline_local_n500.json
```

For all 1,000 rows, change both `--limit` and the output name:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset codex `
    --method pipeline `
    --limit 1000 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 4 `
    --output_file output\experiments\codex_pipeline_local_n1000.json
```

The `closed_book_llm` and `context_llm` baselines use the same command shape as FactKG; change `--dataset` to `codex` and choose a unique output filename.

## 7. Inspect Public-Dataset Results

Summarize a saved result without printing all row-level details:

```powershell
$result = Get-Content output\experiments\factkg_pipeline_local_n500.json -Raw | ConvertFrom-Json
$result |
    Select-Object dataset, method, model_name, provider, total_evaluated, accuracy, ci_95, coverage, selective_accuracy |
    Format-List
```

Inspect the first five errors:

```powershell
$result.results_detail |
    Where-Object { $_.pred -ne $_.gold } |
    Select-Object -First 5 id, claim, gold, pred, raw_pred, reasoning_type |
    Format-List
```

To save terminal logs as well as structured JSON:

```powershell
& .venv\Scripts\python.exe eval_harness.py `
    --dataset factkg `
    --method pipeline `
    --limit 20 `
    --provider local `
    --model_name google/gemma-4-e4b `
    --max_workers 1 `
    --output_file output\experiments\factkg_pipeline_smoke.json `
    2>&1 | Tee-Object -FilePath output\experiments\factkg_pipeline_smoke.log
```

## 8. Do Not Run for Research Evidence

The following entry points are intentionally disabled because they previously generated simulated, label-conditioned, or hand-written statistics:

* `scripts/run_full_experiment_sweep.py`
* `scripts/run_revised_experiments.py`
* `scripts/train_meta_confidence.py`

Do not cite historical numbers in the invalidated benchmark or calibration reports. Check [experiment_registry.md](experiment_registry.md) and `experiments/registry.json` before using any artifact.

## 9. Recommended Run Order

1. Run all tests.
2. Run the RMIT benchmark generator only if the v0 candidate needs regeneration.
3. Generate the expert packet only before review begins.
4. Validate the expert packet.
5. Run the RMIT paired graph-destruction control.
6. Run 20-row FactKG and CoDEx smoke tests with `--max_workers 1`.
7. Inspect the saved JSON files.
8. Freeze model and command settings.
9. Run the selected fixed-size public experiments with unique output filenames.
