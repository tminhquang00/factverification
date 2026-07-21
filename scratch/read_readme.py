import urllib.request

url = "https://raw.githubusercontent.com/yuyuz/MetaQA/master/README.md"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
