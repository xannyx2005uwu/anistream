import cloudscraper
scraper = cloudscraper.create_scraper()
r = scraper.get("https://www.animeunity.so/archivio?title=naruto")
print("Status:", r.status_code)
print("Content sample:", r.text[:200])
