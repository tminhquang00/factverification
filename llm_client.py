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
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "azure").lower()
        
        if self.provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.1-mini")
            
            logger.info(f"Initializing Azure OpenAI Client (Endpoint: {endpoint}, Model: {self.model})")
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint
            )
        else:
            base_url = os.getenv("LOCAL_LLM_API_BASE", "http://localhost:1234/v1")
            self.model = os.getenv("LOCAL_LLM_MODEL_NAME", "qwen2.5-7b-instruct")
            
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

        is_reasoning = "o1" in self.model.lower() or "o3" in self.model.lower() or "gpt-5" in self.model.lower()
        
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        
        if is_reasoning:
            kwargs["max_completion_tokens"] = max(max_tokens, 4096)
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens

        if json_mode:
            # Azure OpenAI and LM Studio support response_format
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error during LLM generation: {e}")
            raise e

    def generate_json(self, prompt: str, system_prompt: str = None, temperature: float = 0.2, max_tokens: int = 4096) -> dict:
        """Helper to generate and parse JSON directly, with fallback if not valid JSON."""
        # Append instructions for JSON format if system_prompt is not explicitly directing it
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
            # Try regex recovery
            import re
            match = re.search(r"\{.*\}", res_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise e

# Singleton instance
_client_instance = None

def get_llm_client() -> LLMClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance
