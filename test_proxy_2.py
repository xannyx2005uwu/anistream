import httpx
print("Starting")
url = "https://www.animeunity.so/archivio?title=naruto"
proxy_url = f"https://api.codetabs.com/v1/proxy?quest={url}"
with httpx.Client(follow_redirects=True, timeout=15.0) as client:
    r = client.get(proxy_url)
    print(f"Status: {r.status_code}")
    print(f"Text snippet: {r.text[:200]}")
