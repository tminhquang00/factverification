import urllib.request
import urllib.error

urls = [
    "https://raw.githubusercontent.com/yuyuz/MetaQA/master/kb.txt",
    "https://github.com/yuyuz/MetaQA/raw/master/kb.txt",
    "https://github.com/yuyuz/MetaQA",
    "https://raw.githubusercontent.com/tsafavi/codex/master/data/triples/codex-s/train.txt"
]

for url in urls:
    print(f"Testing URL: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            print(f"  Status: {response.status}")
            print(f"  Content length: {len(response.read())} bytes")
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error: {e.code} - {e.reason}")
    except Exception as e:
        print(f"  Error: {e}")
