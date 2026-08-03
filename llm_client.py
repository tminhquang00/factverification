import os
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_client")


class UsageMeter:
    """Thread-safe accumulator for per-call token counts and wall-clock latency.

    Every measurement is recorded here rather than derived after the fact, because token cost and
    latency cannot be reconstructed from a finished run. Calls are attributed across threads, so
    totals are safe under the ThreadPoolExecutor the eval harnesses use.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._local = threading.local()
        self.reset()

    def reset(self):
        with self._lock:
            self.n_calls = 0
            self.n_failed_calls = 0
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.total_tokens = 0
            self.n_calls_without_usage = 0
            self.latencies_s = []

    @contextmanager
    def scope(self):
        """Attributes the calls made by the calling thread to one row.

        Each row is evaluated on a single worker thread, but ThreadPoolExecutor reuses threads
        across rows, so the bucket is installed per scope rather than per thread. Yields a dict
        that is populated on exit; global totals accumulate regardless.
        """
        bucket = {
            "n_calls": 0,
            "n_failed_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "n_calls_without_usage": 0,
            "latency_s_sum": 0.0,
        }
        previous = getattr(self._local, "bucket", None)
        self._local.bucket = bucket
        try:
            yield bucket
        finally:
            self._local.bucket = previous

    def record(self, latency_s: float, usage=None, failed: bool = False):
        prompt_t = getattr(usage, "prompt_tokens", None) if usage is not None else None
        completion_t = getattr(usage, "completion_tokens", None) if usage is not None else None
        total_t = getattr(usage, "total_tokens", None) if usage is not None else None
        no_usage = prompt_t is None and completion_t is None and total_t is None
        resolved_total = 0 if no_usage else (total_t or ((prompt_t or 0) + (completion_t or 0)))

        bucket = getattr(self._local, "bucket", None)
        if bucket is not None:
            # Thread-local: no lock needed, only the owning thread touches this bucket.
            bucket["n_calls"] += 1
            bucket["n_failed_calls"] += 1 if failed else 0
            bucket["latency_s_sum"] += latency_s
            if no_usage:
                bucket["n_calls_without_usage"] += 1
            else:
                bucket["prompt_tokens"] += prompt_t or 0
                bucket["completion_tokens"] += completion_t or 0
                bucket["total_tokens"] += resolved_total

        with self._lock:
            self.n_calls += 1
            if failed:
                self.n_failed_calls += 1
            self.latencies_s.append(latency_s)
            if no_usage:
                # Some local servers omit the usage block entirely; count these so a token total
                # is never quoted as complete when part of the run was unmetered.
                self.n_calls_without_usage += 1
                return
            self.prompt_tokens += prompt_t or 0
            self.completion_tokens += completion_t or 0
            self.total_tokens += resolved_total

    def snapshot(self) -> dict:
        with self._lock:
            latencies = sorted(self.latencies_s)
            n = len(latencies)

            def pct(p):
                if not n:
                    return None
                idx = min(n - 1, max(0, int(round(p * (n - 1)))))
                return latencies[idx]

            return {
                "n_calls": self.n_calls,
                "n_failed_calls": self.n_failed_calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
                "n_calls_without_usage": self.n_calls_without_usage,
                "tokens_complete": self.n_calls_without_usage == 0,
                "latency_s": {
                    "sum": sum(latencies) if n else 0.0,
                    "mean": (sum(latencies) / n) if n else None,
                    "p50": pct(0.50),
                    "p95": pct(0.95),
                    "max": latencies[-1] if n else None,
                },
            }


def _uses_completion_token_budget(model_lower: str) -> bool:
    """True for models whose API takes ``max_completion_tokens`` instead of ``max_tokens``.

    Covers the OpenAI o-series (``o1``, ``o3``, ``o4-mini`` and Azure-prefixed variants) and the
    GPT-5 / Azure-5 families. The o-series check is a regex rather than a substring list because
    ``azure-o4-mini`` was silently missed by the previous ``{"o1", "o3"}`` membership test and every
    call to it failed with a 400.
    """
    if re.search(r"(^|[^a-z0-9])o[1-9](-|$|[^a-z0-9])", model_lower):
        return True
    return any(key in model_lower for key in ("gpt-5", "azure-5", "5-mini"))


def _rejects_temperature(model_lower: str) -> bool:
    """True for models that error when ``temperature`` is sent at a value other than the default.

    Three distinct upstream behaviours land here. The o-series and the GPT-5 / Azure-5 families
    reject any value other than 1.0 ("Only temperature=1 is supported"), and the newest Anthropic
    models reject the parameter outright ("`temperature` is deprecated for this model"). In every
    case the only portable fix is to omit the field and accept the provider default.

    That is a genuine confound: these models do not run at the temperature the caller requested.
    Callers record the resolved sampling behaviour in their run manifests so the difference stays
    visible in the results rather than being silently absorbed.

    This predicate is a fast path only. :meth:`LLMClient.generate` also retries without the
    parameter whenever the provider reports it as unsupported, so a model added to the gateway in
    future works without a code change here.
    """
    if _uses_completion_token_budget(model_lower):
        return True
    return bool(re.search(r"claude-opus-4-[7-9]", model_lower))


def _is_unsupported_parameter_error(exc) -> bool:
    """True when the provider rejected a sampling parameter rather than the request itself."""
    text = str(exc).lower()
    markers = (
        "unsupportedparamserror",
        "don't support temperature",
        "only temperature=1 is supported",
        "temperature` is deprecated",
        "temperature is deprecated",
        "unsupported_value",
    )
    return any(marker in text for marker in markers)


def _needs_large_token_budget(model_lower: str) -> bool:
    """True for models that spend output tokens on hidden reasoning before answering.

    Gemini 2.5 Pro returned truncated JSON (``{"verdict": "Not-in-``) at a 512-token budget because
    the thinking trace consumed the allowance. Reasoning-family models have the same failure shape.

    The whole Gemini 2.5 family is covered, not just Pro. Flash was initially left out and then
    produced 7 truncated responses in 1,200 calls during the model panel — rare enough to miss in a
    smoke test, frequent enough to put holes in a results table.
    """
    return _uses_completion_token_budget(model_lower) or "gemini-2.5" in model_lower


class LLMClient:
    def __init__(self, provider: str = None, model: str = None, base_url: str = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "azure")).lower()
        self.usage = UsageMeter()
        # Set when a provider rejects `temperature` at runtime, so manifests can record that the
        # requested sampling temperature was not actually applied.
        self._temperature_unsupported = False

        if self.provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.model = model or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "azure-4.1-mini")
            
            logger.info(f"Initializing Azure OpenAI Client (Endpoint: {endpoint}, Model: {self.model})")
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint
            )
        else:
            base_url = base_url or os.getenv("LOCAL_LLM_API_BASE", "http://localhost:1234/v1")
            self.model = model or os.getenv("LOCAL_LLM_MODEL_NAME", "google/gemma-4-e4b")
            
            logger.info(f"Initializing Local OpenAI Client (Base URL: {base_url}, Model: {self.model})")
            self.client = OpenAI(
                api_key="lm-studio",
                base_url=base_url
            )

    def resolved_sampling(self, requested_temperature: float = None) -> dict:
        """Describes how this model actually samples, for recording in run manifests.

        A run that asks for ``temperature=0.0`` does not get it on every model. The o-series, the
        GPT-5 / Azure-5 families and the newest Anthropic models all run at a provider default
        instead. Cross-model comparisons must disclose that, because part of any observed
        difference between such a model and a temperature-0 model is sampling, not capability.
        """
        model_lower = self.model.lower()
        honoured = not _rejects_temperature(model_lower) and not getattr(
            self, "_temperature_unsupported", False
        )
        return {
            "model": self.model,
            "provider": self.provider,
            "requested_temperature": requested_temperature,
            "temperature_honoured": honoured,
            "effective_temperature": requested_temperature if honoured else "provider_default",
            "token_budget_parameter": (
                "max_completion_tokens"
                if _uses_completion_token_budget(model_lower) else "max_tokens"
            ),
        }

    def generate(self, prompt: str, system_prompt: str = None, json_mode: bool = False, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        model_lower = self.model.lower()
        kwargs = {
            "model": self.model,
            "messages": messages,
        }

        # Token budget: reasoning families take max_completion_tokens, everything else max_tokens.
        # Models that think before answering need headroom or the visible answer gets truncated.
        budget = max(max_tokens, 4096) if _needs_large_token_budget(model_lower) else max_tokens
        if _uses_completion_token_budget(model_lower):
            kwargs["max_completion_tokens"] = budget
        else:
            kwargs["max_tokens"] = budget

        # Temperature: omitted entirely for models that reject the parameter. This means those
        # models run at their provider default rather than the temperature the caller asked for,
        # which is a real confound and is recorded by callers in their run manifests.
        if not _rejects_temperature(model_lower):
            kwargs["temperature"] = temperature

        if json_mode and self.provider == "azure":
            kwargs["response_format"] = {"type": "json_object"}


        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
            self.usage.record(time.perf_counter() - started, getattr(response, "usage", None))
            return response.choices[0].message.content
        except Exception as e:
            self.usage.record(time.perf_counter() - started, None, failed=True)
            # A model the predicates above do not yet know about may still reject `temperature`.
            # Drop it and retry once so a newly added gateway model works without a code change.
            # The resolved sampling behaviour is surfaced by `resolved_sampling()` for manifests.
            if "temperature" in kwargs and _is_unsupported_parameter_error(e):
                logger.warning(
                    "Model %s rejected the temperature parameter; retrying at the provider "
                    "default and recording the substitution. Error: %s", self.model, e
                )
                kwargs.pop("temperature", None)
                self._temperature_unsupported = True
                retry_started = time.perf_counter()
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    self.usage.record(time.perf_counter() - retry_started,
                                      getattr(response, "usage", None))
                    return response.choices[0].message.content
                except Exception as retry_error:
                    self.usage.record(time.perf_counter() - retry_started, None, failed=True)
                    e = retry_error
            # Fallback if response_format is not supported by local model
            if json_mode and "response_format" in kwargs:
                logger.warning(f"Retrying generation without response_format due to error: {e}")
                kwargs.pop("response_format", None)
                retry_started = time.perf_counter()
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    self.usage.record(time.perf_counter() - retry_started, getattr(response, "usage", None))
                    return response.choices[0].message.content
                except Exception as e2:
                    self.usage.record(time.perf_counter() - retry_started, None, failed=True)
                    logger.error(f"Error during fallback LLM generation: {e2}")
                    raise e2
            logger.error(f"Error during LLM generation: {e}")
            raise e

    def generate_json(self, prompt: str, system_prompt: str = None, temperature: float = 0.2, max_tokens: int = 4096) -> dict:
        """Helper to generate and parse JSON directly, with fallback if not valid JSON."""
        json_instruction = "\nIMPORTANT: You must respond with a raw JSON object ONLY. Do not wrap it in markdown code blocks like ```json or similar formatting."
        
        full_prompt = prompt
        if json_instruction not in full_prompt:
            full_prompt += json_instruction
            
        res_text = self.generate(full_prompt, system_prompt=system_prompt, json_mode=True, temperature=temperature, max_tokens=max_tokens)
        
        # Clean any accidental markdown code fences
        res_text = res_text.strip()
        if res_text.startswith("```"):
            lines = res_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            res_text = "\n".join(lines).strip()
            
        try:
            return json.loads(res_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {res_text}. Error: {e}")
            import re
            match = re.search(r"\{.*\}", res_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise e

    def generate_batch(self, prompts: list, system_prompt: str = None, json_mode: bool = False, max_workers: int = 10, **kwargs) -> list:
        """Executes a list of prompts in parallel using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = [None] * len(prompts)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.generate, prompt, system_prompt=system_prompt, json_mode=json_mode, **kwargs): i
                for i, prompt in enumerate(prompts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Error in batch generation item {idx}: {e}")
                    results[idx] = ""
        return results

    def generate_json_batch(self, prompts: list, system_prompt: str = None, max_workers: int = 10, **kwargs) -> list:
        """Executes a list of prompts in parallel using ThreadPoolExecutor for JSON output."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = [None] * len(prompts)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.generate_json, prompt, system_prompt=system_prompt, **kwargs): i
                for i, prompt in enumerate(prompts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Error in batch JSON generation item {idx}: {e}")
                    results[idx] = {"verdict": "Not-in-KG", "reason": f"Batch error: {e}", "evidence": []}
        return results

_client_instance = None

def get_llm_client(provider: str = None, model: str = None, base_url: str = None) -> LLMClient:
    global _client_instance
    if provider is not None or model is not None or _client_instance is None:
        _client_instance = LLMClient(provider=provider, model=model, base_url=base_url)
    return _client_instance

