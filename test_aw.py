import httpx
try:
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        r = client.get("https://www.animeworld.so/api/search/v2", params={"keyword": "naruto"}, headers={"User-Agent": "Mozilla/5.0"})
        print(f"Status: {r.status_code}")
        print(f"JSON keys: {r.json().keys() if r.status_code == 200 else r.text[:100]}")
except Exception as e:
    print(f"Error: {e}")
