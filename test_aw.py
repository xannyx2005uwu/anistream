import os
import animeworld as aw

print("Trying aw.find...")
try:
    print(aw.find("naruto"))
except Exception as e:
    print("Exception", e)
    res = aw.SES.post("/api/search/v2?", params={"keyword": "naruto"}, follow_redirects=True)
    print("STATUS", res.status_code)
    print("HEADERS", res.headers)
    print("CONTENT", res.text[:500])
