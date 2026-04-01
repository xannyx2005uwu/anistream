from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import animeworld as aw
import os
import httpx
import json

app = FastAPI(title="Anistream API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ANILIST_URL = "https://graphql.anilist.co"

def anilist_query(query: str, variables: dict = None):
    try:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        with httpx.Client(timeout=10.0) as client:
            res = client.post(ANILIST_URL, json=payload)
            res.raise_for_status()
            return res.json().get("data", {})
    except Exception as e:
        print("Anilist Query Error:", e)
        return {}

def format_anilist_media(media_list):
    fmt = []
    for m in media_list:
        if not m: continue
        title = m.get("title", {}).get("english") or m.get("title", {}).get("romaji") or "Unknown"
        img = m.get("coverImage", {}).get("extraLarge") or m.get("coverImage", {}).get("large") or ""
        score = (m.get("averageScore") or 0) / 10.0
        cats = [{"name": c} for c in m.get("genres", [])]
        fmt.append({
            "id": m.get("id"),
            "name": title,
            "romajiTitle": m.get("title", {}).get("romaji"),
            "link": f"/play/{m.get('id')}",
            "image": img,
            "malVote": round(score, 1) if score else None,
            "categories": cats
        })
    return fmt

@app.get("/api/home")
def get_home_data():
    query = """
    query {
      trending: Page(perPage: 15) {
        media(sort: TRENDING_DESC, type: ANIME, isAdult: false) { id title { romaji english } coverImage { extraLarge } averageScore genres }
      }
      action: Page(perPage: 15) {
        media(genre: "Action", sort: POPULARITY_DESC, type: ANIME, isAdult: false) { id title { romaji english } coverImage { extraLarge } averageScore genres }
      }
      comedy: Page(perPage: 15) {
        media(genre: "Comedy", sort: POPULARITY_DESC, type: ANIME, isAdult: false) { id title { romaji english } coverImage { extraLarge } averageScore genres }
      }
      romance: Page(perPage: 15) {
        media(genre: "Romance", sort: POPULARITY_DESC, type: ANIME, isAdult: false) { id title { romaji english } coverImage { extraLarge } averageScore genres }
      }
      fantasy: Page(perPage: 15) {
        media(genre: "Fantasy", sort: POPULARITY_DESC, type: ANIME, isAdult: false) { id title { romaji english } coverImage { extraLarge } averageScore genres }
      }
    }
    """
    data = anilist_query(query)
    
    response_data = {
        "Nuove Uscite": format_anilist_media(data.get("trending", {}).get("media", [])),
        "Azione": format_anilist_media(data.get("action", {}).get("media", [])),
        "Commedia": format_anilist_media(data.get("comedy", {}).get("media", [])),
        "Romantica": format_anilist_media(data.get("romance", {}).get("media", [])),
        "Fantasy": format_anilist_media(data.get("fantasy", {}).get("media", []))
    }
    return {"data": response_data}

@app.get("/api/search")
def search_anime(keyword: str = Query(..., description="The search query")):
    query = """
    query($search: String) {
      Page(perPage: 20) {
        media(search: $search, type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
          id title { romaji english } coverImage { extraLarge } averageScore genres
        }
      }
    }
    """
    data = anilist_query(query, {"search": keyword})
    results = format_anilist_media(data.get("Page", {}).get("media", []))
    return {"data": results}

@app.get("/api/anime")
def get_anime_details(id: int = Query(..., description="The Anilist ID")):
    query = """
    query($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title { romaji english }
        description
        coverImage { extraLarge }
        bannerImage
        averageScore
        episodes
        nextAiringEpisode { episode }
        status
        genres
        relations {
          edges {
            relationType
            node {
              id
              title { romaji english }
              type
            }
          }
        }
      }
    }
    """
    data = anilist_query(query, {"id": id})
    media = data.get("Media")
    if not media:
        raise HTTPException(status_code=404, detail="Anime not found on Anilist")
    
    title = media.get("title", {}).get("english") or media.get("title", {}).get("romaji") or "Unknown"
    score = (media.get("averageScore") or 0) / 10.0
    
    ep_count = media.get("episodes")
    next_air = media.get("nextAiringEpisode")
    if next_air and isinstance(next_air, dict) and "episode" in next_air:
        # Se c'è un episodio futuro in onda, l'ultimo uscito è quello precedente
        ep_count = next_air["episode"] - 1
        
    episodes = ep_count if ep_count else "?"
    
    from bs4 import BeautifulSoup
    raw_desc = media.get("description") or ""
    clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text()

    raw_relations = media.get("relations", {}).get("edges", [])
    valid_relations = ["SEQUEL", "PREQUEL", "ALTERNATIVE", "PARENT", "SIDE_STORY", "SPIN_OFF"]
    seasons = []
    for edge in raw_relations:
        if edge.get("relationType") in valid_relations and edge.get("node", {}).get("type") == "ANIME":
            node = edge["node"]
            seasons.append({
                "id": node["id"],
                "title": node.get("title", {}).get("english") or node.get("title", {}).get("romaji"),
                "relation": edge.get("relationType")
            })

    return {
        "name": title,
        "romajiTitle": media.get("title", {}).get("romaji"),
        "englishTitle": media.get("title", {}).get("english"),
        "trama": clean_desc,
        "cover": media.get("bannerImage") or media.get("coverImage", {}).get("extraLarge") or "",
        "poster": media.get("coverImage", {}).get("extraLarge") or "",
        "info": {
            "Episodi": str(episodes),
            "Voto": round(score, 1) if score else "N/A",
            "Stato": media.get("status", ""),
            "Generi": ", ".join(media.get("genres", []))
        },
        "seasons": seasons
    }

import difflib
import re

def get_aw_animelink(title: str, english_title: str = None):
    import urllib.parse
    from bs4 import BeautifulSoup

    # Score against romaji AND english title, take the best
    def match_score(found_name):
        s = difflib.SequenceMatcher(None, title.lower(), found_name.lower()).ratio()
        if english_title:
            s2 = difflib.SequenceMatcher(None, english_title.lower(), found_name.lower()).ratio()
            s = max(s, s2)
        return s

    # Build progressive keyword candidates from most specific to least
    search_keywords = []
    search_keywords.append(title)
    if english_title and english_title.lower() != title.lower():
        search_keywords.append(english_title)
    # Romaji without season suffix
    clean_rom = re.sub(r'\s*(\d+(st|nd|rd|th) Season|Season \d+|Part \d+)$', '', title, flags=re.IGNORECASE).strip()
    if clean_rom and clean_rom not in search_keywords:
        search_keywords.append(clean_rom)
    # Romaji base (before colon)
    if ":" in title:
        base = title.split(":")[0].strip()
        if base not in search_keywords:
            search_keywords.append(base)
    # English base (before colon) — key for "Frieren: Beyond..." -> "Frieren"
    if english_title and ":" in english_title:
        base_en = english_title.split(":")[0].strip()
        if base_en not in search_keywords:
            search_keywords.append(base_en)
    # First meaningful word of English title as last resort
    if english_title:
        first_word = english_title.split()[0]
        if len(first_word) > 4 and first_word not in search_keywords:
            search_keywords.append(first_word)

    best_link = None
    best_score = -1

    for keyword in search_keywords:
        try:
            results = aw.find(keyword)
            if results:
                for r in results:
                    score = match_score(r.get("name", ""))
                    if score > best_score:
                        best_score = score
                        best_link = r["link"]
                if best_score > 0.65:
                    print(f"Found via aw.find! keyword='{keyword}', score={best_score:.2f}")
                    return best_link
        except Exception:
            pass

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                res = client.get(
                    f"https://www.animeworld.ac/filter?keyword={urllib.parse.quote(keyword)}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                soup = BeautifulSoup(res.text, "html.parser")
                items = soup.select(".film-list .item a.name")
                for item in items:
                    name_found = item.get_text(strip=True)
                    score = match_score(name_found)
                    if score > best_score:
                        best_score = score
                        best_link = "https://www.animeworld.ac" + item["href"]
                if best_score > 0.65:
                    print(f"Found via HTML scrape! keyword='{keyword}', score={best_score:.2f}")
                    return best_link
        except Exception:
            pass

    if best_score > 0.65:
        return best_link
    return None

@app.get("/api/episodes")
def get_anime_episodes(
    title: str = Query(..., description="The anime romaji title"),
    en: str = Query(None, description="The anime English title (fallback)"),
    c: int = Query(None, description="Total episodes count from anilist")
):
    try:
        if not title or title.strip() == "None": raise Exception("Invalid title")
        aw_link = get_aw_animelink(title, english_title=en)
        if not aw_link:
            raise Exception("Cannot find anime in AnimeWorld via title search")
        
        anime = aw.Anime(aw_link)
        episodes = anime.getEpisodes()
        eps_data = []
        for ep in episodes:
            raw_url = getattr(ep.links[0], 'link', '') if len(ep.links) > 0 else ''
            # Se è un direct download di SweetPixel, convertilo in un link MP4 puro per streaming
            if "download-file.php?id=" in raw_url:
                raw_url = raw_url.replace("download-file.php?id=", "")
            
            eps_data.append({
                "number": ep.number,
                "link": raw_url,
            })

        if not eps_data: raise Exception("No episodes found natively")
        return {"data": eps_data}
    except Exception as e:
        print("Fallback episodes:", e)
        # Se 'c' non è fornito (anime non ancora uscito / count '?'), mostra solo 1 placeholder invece di 24 fake.
        target_c = c if c is not None else 1
        max_eps = max(1, min(target_c, 5000))
        # Use a nice UI data-URI instead of a blocked iframe
        html_content = "<html><body style='background:#111;color:#a855f7;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;text-align:center'><h2>Episodio in Arrivo / Stream Non Trovato</h2></body></html>"
        import urllib.parse
        data_uri = "data:text/html;charset=utf-8," + urllib.parse.quote(html_content)
        
        eps_data = [
            {"number": str(i+1), "link": data_uri} for i in range(max_eps)
        ]
        return {"data": eps_data}

# Serve the static files (Frontend code)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    target_path = os.path.join(static_dir, full_path)
    if os.path.isfile(target_path):
        return FileResponse(target_path)
    return FileResponse(os.path.join(static_dir, "index.html"))
