# KG Verification Framework - Implementation Plan

This document outlines the step-by-step plan to implement the Knowledge Graph (KG) verification framework based on the provided design document. The plan focuses on setting up public baselines, building a local KG from RMIT crawled data, generating a multi-reasoning dataset, and constructing a modular verification pipeline that works with both Azure OpenAI and local LLMs (e.g., LM Studio).

## User Review Required

> [!IMPORTANT]
> **LLM Egress & Performance Constraints**
> Local deployment (LM Studio/Ollama) is planned as a core requirement. Quantized 7B/8B models (e.g., Qwen2.5-7B, Llama-3.1-8B) on consumer hardware will have higher extraction/mapping error rates compared to GPT-5 Mini. We will design the extraction consistency checking (double runs) to mitigate this.

> [!NOTE]
> **Knowledge Graph Storage Format**
> To keep the pipeline portable and avoid complex local database server installations, we propose starting with a local file-based RDF store using `rdflib` or SQLite graph representation for the benchmark harness. We can add Neo4j integration later once the core pipeline logic is validated.

## Open Questions

- **Do you want to run the full crawl first, or should we use the currently crawled data?**
  The crawled outputs in `output/` contain course files (e.g. `001034_Biology.txt`). We can start parsing this data immediately.
- **Which local model from LM Studio do you plan to use?**
  We recommend Llama-3.1-8B-Instruct or Qwen2.5-7B-Instruct as they are excellent at structured JSON output.

---

## Proposed Changes

### 1. Project Infrastructure & Unified LLM Client

Initialize project structure, environment configurations, and the LLM execution layer.

#### [NEW] [llm_client.py](file:///c:/Users/Admin/Desktop/crawler/llm_client.py)
A unified client interface wrapper around `openai` SDK.
- Handles switching between Azure OpenAI (using the provided credentials) and local LM Studio (via `base_url="http://localhost:1234/v1"`).
- Automatically handles parsing, retries, and rate-limiting.

#### [NEW] [.env](file:///c:/Users/Admin/Desktop/crawler/.env)
Configuration parameters for Azure OpenAI and Local LLM.
```ini
# LLM Provider: "azure" or "local"
LLM_PROVIDER=azure

# Azure Configuration
AZURE_OPENAI_API_KEY=<your_azure_openai_api_key>
AZURE_OPENAI_ENDPOINT=https://bgsv-sx-gpt.openai.azure.com/
AZURE_OPENAI_API_VERSION=2025-03-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.1-mini

# Local LM Studio Configuration
LOCAL_LLM_API_BASE=http://localhost:1234/v1
LOCAL_LLM_MODEL_NAME=qwen2.5-7b-instruct
```

---

### 2. Public Dataset Baseline Setup

Establish verification baselines on standard public datasets.

#### [NEW] [eval_harness.py](file:///c:/Users/Admin/Desktop/crawler/eval_harness.py)
The core benchmark execution runner.
- Defines the `DatasetAdapter` interface.
- Runs verification over normalized JSONL data.
- Computes metrics: Precision, Recall, F1, Accuracy, and per-reasoning-type performance.

#### [NEW] [adapters/factkg_adapter.py](file:///c:/Users/Admin/Desktop/crawler/adapters/factkg_adapter.py)
Adapter for the **FactKG** dataset (Kim et al., ACL 2023).
- Parses claims and maps the 5 reasoning types: One-hop, Conjunction, Existence, Multi-hop, Negation.
- Performs target evaluation using the DBpedia-lite graph context provided by FactKG.

#### [NEW] [adapters/fever_adapter.py](file:///c:/Users/Admin/Desktop/crawler/adapters/fever_adapter.py)
Adapter for the **FEVER** dataset.
- Focuses on validation of the tri-state classification, mapping FEVER's `NotEnoughInfo` to our `Not-in-KG` state.

---

### 3. RMIT Knowledge Graph Construction

Construct a clean, structured graph representation from the handbook files crawled from RMIT.

#### [NEW] [parse_handbook.py](file:///c:/Users/Admin/Desktop/crawler/parse_handbook.py)
Parses the cached RMIT handbook files (`.txt` and `.html`) in `output/Study Type/Courses` and `output/Study Area`.
- Extracts Course entities (code, title, credits, term).
- Identifies prerequisite, corequisite, and exclusion lists using regex and pattern matching.
- Saves structured triples into an RDF graph (e.g. Turtle format `.ttl`) or a local SQLite database.

#### [NEW] [kg_store.py](file:///c:/Users/Admin/Desktop/crawler/kg_store.py)
A lightweight wrapper for querying the local graph.
- Implements simple RDF lookup queries (e.g., finding prerequisites, course credits, terms).
- Declares open-world vs closed-world status for each relation schema (e.g., `requiresPrerequisite` is closed-world; `taughtBy` is open-world).

---

### 4. Reasoning Dataset Generator

Generate an administrative fact-checking gold dataset derived from the RMIT KG.

#### [NEW] [generate_dataset.py](file:///c:/Users/Admin/Desktop/crawler/generate_dataset.py)
Generates evaluation records containing authentic facts, perturbed facts, and reasoning annotations.
- **One-hop**: Direct lookup of properties (e.g., CS101 has 12 credits).
- **Conjunction**: Combinations of prerequisites or terms (e.g., CS101 is offered in Semester 1 AND requires CS100).
- **Existence**: Fact check on course existence or offerings (e.g., RMIT offers a course named 'Biology').
- **Multi-hop**: Transitive paths (e.g., CS201 requires CS101, which requires CS100).
- **Negation**: Asserting a course is NOT offered or does NOT have a prerequisite.
- Generates golden labels: `Supported` (factual), `Contradicted` (perturbed/inconsistent facts), `Not-in-KG` (entities/relations not present in the graph).

---

### 5. Post-Hoc Verification Pipeline

Implement the stage-by-stage architecture.

#### [NEW] [verification_pipeline.py](file:///c:/Users/Admin/Desktop/crawler/verification_pipeline.py)
Coordinates the verification stages:
- **Stage 2 (Decomposition)**: Prompts the LLM to extract atomic claims as schema-constrained JSON structures (using double runs for self-consistency).
- **Stage 3 (Mapping)**: Maps claims to triples using deterministic matching (regex for course codes) or embedding-based entity linking.
- **Stage 4 (Engine)**: Evaluates triples against the local RMIT KG using semantics-dispatched verification (closed-world vs open-world checks) and returns `Supported`, `Contradicted`, or `Not-in-KG`.
- **Stage 5 (Report)**: Generates a JSON/Markdown report showing each claim, its verdict, reasons, and evidence.

---

## Verification Plan

### Automated Tests
- Run unit tests to check LLM Client initialization and provider routing:
  `python -m unittest tests/test_llm_client.py`
- Run KG queries validation to ensure proper loading of RMIT data:
  `python parse_handbook.py --test-limit 10`
- Run verification harness on a mock slice of FactKG:
  `python eval_harness.py --dataset factkg --limit 20`

### Manual Verification
- Review the generated RMIT reasoning dataset to check quality of prompt paraphrases.
- Verify generated verification reports to confirm `Supported`, `Contradicted`, and `Not-in-KG` verdicts correspond exactly to the ground truth facts.
