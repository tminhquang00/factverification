import os
import json
import logging
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_client")

class LLMClient:
    def __init__(self, provider: str = None, model: str = None, base_url: str = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "azure")).lower()
        
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

    def generate(self, prompt: str, system_prompt: str = None, json_mode: bool = False, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        model_lower = self.model.lower()
        is_reasoning = any(k in model_lower for k in ["o1", "o3", "gpt-5", "azure-5", "5-mini"])
        
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        
        if is_reasoning:
            kwargs["max_completion_tokens"] = max(max_tokens, 4096)
            # gpt-5/azure-5 models require temperature=1.0 or omit temperature
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            # Fallback if response_format is not supported by local model
            if json_mode and "response_format" in kwargs:
                logger.warning(f"Retrying generation without response_format due to error: {e}")
                kwargs.pop("response_format", None)
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content
                except Exception as e2:
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

