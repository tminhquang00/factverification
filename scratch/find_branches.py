import urllib.request
import re

url = "https://github.com/yuyuz/MetaQA"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
    
    # Look for branch selector or file paths
    print("Searching branch names...")
    branches = re.findall(r'/yuyuz/MetaQA/tree/([a-zA-Z0-9_\-]+)', html)
    print("Found tree branch paths:", set(branches))
    
    # Look for files ending in .txt
    print("Searching .txt files...")
    txt_files = re.findall(r'/yuyuz/MetaQA/blob/[a-zA-Z0-9_\-]+/([a-zA-Z0-9_\-\/]+\.txt)', html)
    print("Found .txt file paths:", set(txt_files))
    
except Exception as e:
    print("Error:", e)
