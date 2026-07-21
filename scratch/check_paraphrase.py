import llm_client
client = llm_client.get_llm_client()
sys_prompt = "You are an administrative assistant. Paraphrase the provided factual statement into a natural-sounding query, question, or statement that a university student or administrator might write. Do not change the core facts, names, or codes. Respond with the paraphrased sentence ONLY."
prompt = 'Factual Statement: "Course 052482 (Textile Practice Research Strategies) is worth 12 credit points."\n\nParaphrased:'
print("Result:", repr(client.generate(prompt, system_prompt=sys_prompt)))
