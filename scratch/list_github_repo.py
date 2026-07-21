import urllib.request
import json

url = "https://api.github.com/repos/yuyuz/MetaQA/contents"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        contents = json.loads(response.read().decode('utf-8'))
    for item in contents:
        print(f"{item['name']} ({item['type']})")
except Exception as e:
    print("Error:", e)
