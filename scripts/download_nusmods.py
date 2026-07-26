import os
import json
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_nusmods")

NUSMODS_BASE_URL = "https://api.nusmods.com/v2"
ACADEMIC_YEARS = ["2025-2026", "2024-2025", "2023-2024", "2022-2023", "2021-2022", "2020-2021"]
ENDPOINTS = ["moduleList.json", "moduleInformation.json", "modules.json"]
OUTPUT_DIR = "data/nusmods"

def download_file(url: str, dest_path: str) -> bool:
    logger.info(f"Downloading {url} -> {dest_path}")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read()
            # Verify JSON
            data = json.loads(content.decode("utf-8"))
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        logger.info(f"Saved {dest_path} (size: {os.path.getsize(dest_path)} bytes)")
        return True
    except urllib.error.HTTPError as e:
        logger.warning(f"HTTP {e.code} for {url}")
        return False
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False

def main():
    successful_downloads = []
    for ay in ACADEMIC_YEARS:
        for ep in ENDPOINTS:
            url = f"{NUSMODS_BASE_URL}/{ay}/{ep}"
            filename = f"{ay}_{ep}"
            dest_path = os.path.join(OUTPUT_DIR, filename)
            if download_file(url, dest_path):
                successful_downloads.append(dest_path)
                
    logger.info(f"Successfully downloaded {len(successful_downloads)} dataset files into {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
