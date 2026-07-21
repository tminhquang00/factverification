# Workspace Behavioral Rules & Agent Instructions

This document governs agent instructions, style guides, and evaluation protocols for the Knowledge Graph Verification Framework repository. All agents pair-programming in this workspace must adhere strictly to these guidelines.

---

## 1. Code Integrity & Style Constraints

*   **Preserve Documentation**: Retain all existing docstrings, class comments, and inline developer comments unless explicitly asked to modify them.
*   **Thread Safety**: `KGStore` instances must remain thread-safe. Keep catalog mutations isolated and read operations fast to support concurrent LLM evaluation harnesses.
*   **Isolated Index Rebuilds**: Always clear class-level caches (like `self.entity_index` inside `VerificationPipeline`) when shifting context or loading dynamic graph samples to prevent evaluation data leakage.

---

## 2. Evaluation & Harness Standards

*   **Forced-Decision Label Normalization**:
    *   For binary datasets like **FactKG** (Supported vs. Contradicted), map pipeline/model uncertainty outcomes (`Not-in-KG`, `Out-of-scope`) to `Contradicted` to ensure correct alignment with target labels.
*   **Confidence Intervals**:
    *   Do not claim F1/accuracy deltas as valid findings unless they exceed the statistical 95% Confidence Interval noise band.
    *   Compute intervals using standard bootstrap sampling (1,000 runs) when generating comparative reports.
*   **Coverage & Selection Separation**:
    *   Always split pipeline evaluations into **Coverage** (fraction of resolved, in-scope claims) and **Selective Accuracy** (accuracy computed only on the covered subset). Do not report raw pipeline accuracy in isolation.
*   **FEVER Exclusions**:
    *   Do not attempt to execute context-based LLM or structured pipeline verifiers on **FEVER** or **Climate-FEVER** text-evidence samples. Report these runs as `N/A (unstructured text evidence, not triples)`.

---

## 3. Environment & Execution Guidelines

*   **Venv Execution**: Always execute scripts and harness commands using the local virtual environment Python executable:
    ```powershell
    & .venv\Scripts\python.exe <script_path>
    ```
*   **Persistent Density Estimations**: Estimate relation density and completeness metrics over the global catalog store, not per-sample transient graphs, to avoid degenerate completeness calculations on tiny graphs.
