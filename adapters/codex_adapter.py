import os
import json
import logging

logger = logging.getLogger("codex_adapter")

class CoDExAdapter:
    def __init__(self, data_path="data/codex_test.jsonl"):
        self.data_path = data_path

    def load_data(self):
        """Loads CoDEx claims dataset."""
        if os.path.exists(self.data_path):
            logger.info(f"Loading CoDEx data from {self.data_path}")
            data = []
            with open(self.data_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
            return data
        else:
            logger.error(f"CoDEx-S dataset not found at {self.data_path}")
            return []
