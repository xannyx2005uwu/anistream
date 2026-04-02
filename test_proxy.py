import httpx
print("Starting script")
try:
    with httpx.Client(follow_redirects=True, timeout=15.0) as client:
        r = client.get("https://api.codetabs.com/v1/proxy?quest=https://www.animeunity.so/info_api/4122/0")
        print(f"Status: {r.status_code}")
        print(f"Text len: {len(r.text)}")
except Exception as e:
    print(f"Error: {e}")
