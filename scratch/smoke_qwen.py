import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["LLM_PROVIDER"] = "local"
os.environ["LOCAL_LLM_MODEL_NAME"] = "qwen/qwen3.5-9b"

from llm_client import get_llm_client

c = get_llm_client(provider="local", model="qwen/qwen3.5-9b")
prompt = (
    'Claim: "Paris is the capital of France." '
    'Evidence: [{"subject":"Paris","predicate":"capitalOf","object":"France"}]. '
    'Respond with JSON: {"verdict": "Supported|Contradicted|Not-in-KG", "reason": "...", "evidence": []}'
)
t0 = time.time()
res = c.generate_json(
    prompt,
    system_prompt="You are a fact verification engine. Respond only with JSON.",
    temperature=0.1,
    max_tokens=4096,
)
print("elapsed", time.time() - t0)
print(res)
