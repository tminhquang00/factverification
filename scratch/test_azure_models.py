import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from llm_client import LLMClient

models = ["azure-4.1-mini", "azure-5-mini", "azure-4.1"]

for m in models:
    try:
        client = LLMClient(provider="azure", model=m)
        res = client.generate("Say hello in one word", max_tokens=20)
        print(f"[SUCCESS] {m}: {res.strip()}")
    except Exception as e:
        print(f"[ERROR] {m}: {e}")
