from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import httpx
import json

# ======================== ANIMEUNITY CLIENT ========================
from bs4 import BeautifulSoup
import difflib
import re

AU_BASE = "https://www.animeunity.so"
from typing import Optional
_au_client: Optional[httpx.Client] = None

def get_au_client() -> httpx.Client:
    global _au_client
    if _au_client is None:
        _au_client = httpx.Client(
            timeout=4.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
                "Referer": AU_BASE,
            }
        )
        try:
            _au_client.get(AU_BASE)  # Init session / get cookies
        except Exception:
            pass
    return _au_client

def au_normalize(text: str) -> str:
    """Port of the TypeScript _normalizeQuery used by AnimeUnity providers."""
    if not text: return ""
    s = text
    s = re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', s, flags=re.IGNORECASE)  # 2nd -> 2
    s = re.sub(r'(\d+)\s*Season', r'\1', s, flags=re.IGNORECASE)           # 2 Season -> 2
    s = re.sub(r'Season\s*(\d+)', r'\1', s, flags=re.IGNORECASE)           # Season 2 -> 2
    extras = r'\b(EXTRA PART|OVA|SPECIAL|RECAP|FINAL SEASON|BONUS|SIDE STORY|PART\s*\d+|EPISODE\s*\d+)\b'
    s = re.sub(extras, '', s, flags=re.IGNORECASE)
    s = re.sub(r'-.*?-', '', s)              # remove -...-
    s = re.sub(r'\bThe(?=\s+Movie\b)', '', s, flags=re.IGNORECASE)
    s = s.replace('~', ' ').replace('.', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    # Cut at first non-ASCII to match how AU indexes Japanese titles
    m = re.search(r'[^\x00-\x7F]', s)
    if m: s = s[:m.start()].strip()
    return s.lower()

def au_build_hints(title: str, english_title: str = None) -> list:
    """Generate all keyword variants to try on AnimeUnity /archivio."""
    candidates = []
    for t in [title, english_title]:
        if not t: continue
        candidates.append(t.lower())
        candidates.append(au_normalize(t))
        # without 'Season' word
        no_season = re.sub(r'\s*(\d+(st|nd|rd|th)\s*Season|Season\s*\d+)', '', t, flags=re.IGNORECASE).strip()
        if no_season: candidates.append(no_season.lower())
        # base before colon
        if ':' in t:
            candidates.append(t.split(':')[0].strip().lower())
        # subtitle after colon
        if ':' in t:
            sub = t.split(':', 1)[1].strip()
            if len(sub) > 3: candidates.append(sub.lower())
        # first word only (if long enough)
        first = t.split()[0]
        if len(first) > 3: candidates.append(first.lower())
    # Deduplicate preserving order
    seen = set()
    return [x for x in candidates if x and not (x in seen or seen.add(x))][:3]

def au_search_both(anilist_id: int, title_hints: list) -> tuple[Optional[dict], Optional[dict]]:
    """Find both sub and dub on AnimeUnity using AniList ID."""
    client = get_au_client()

    # Expand hints with all keyword variants
    expanded = []
    for h in title_hints:
        expanded += au_build_hints(h)
    expanded = title_hints + expanded
    seen_q: set = set()
    queries = [q.strip() for q in expanded if q and q.strip() not in seen_q and not seen_q.add(q.strip())]

    # Collect all records seen during search for secondary title-match pass
    all_records_by_query: dict = {}
    
    sub_record = None
    dub_record = None

    for query in queries:
        if not query or len(query) < 2: continue
        if sub_record and dub_record: break # found both

        try:
            res = client.get(f"{AU_BASE}/archivio", params={"title": query}, timeout=4.0)
            if res.status_code in [403, 429, 503]:
                print(f"AU Blocked by Cloudflare! Status: {res.status_code}")
                break
                
            soup = BeautifulSoup(res.text, "html.parser")
            tag = soup.find("archivio")
            if not tag: continue
            records = json.loads(tag.get("records", "[]"))
            if not records: continue

            all_records_by_query[query] = records

            # ── Pass 1: exact AniList ID ──
            if not sub_record:
                matches = [r for r in records if str(r.get("anilist_id")) == str(anilist_id) and r.get("dub") == 0]
                if matches:
                    print(f"AnimeUnity ✓ [sub] anilist={anilist_id} via '{query}'")
                    sub_record = matches[0]
            
            if not dub_record:
                matches = [r for r in records if str(r.get("anilist_id")) == str(anilist_id) and r.get("dub") == 1]
                if matches:
                    print(f"AnimeUnity ✓ [dub] anilist={anilist_id} via '{query}'")
                    dub_record = matches[0]

        except Exception as e:
            print(f"AU search error for '{query}': {e}")
            if "Timeout" in str(e) or "429" in str(e) or "403" in str(e):
                break

    # ── Pass 2: title-based fuzzy match (catches AU/AniList ID mismatches) ──
    ref_title = (title_hints[0] if title_hints else "").lower()
    
    def fuzzy_match(want_dub: bool):
        dub_val = 1 if want_dub else 0
        best_score = 0.0
        best_r = None
        for query, records in all_records_by_query.items():
            for r in records:
                if r.get("dub", 0) != dub_val: continue
                for field in ["title_eng", "title", "title_it", "slug"]:
                    val = (r.get(field) or "").lower().replace("-", " ")
                    if not val: continue
                    score = difflib.SequenceMatcher(None, ref_title, val).ratio()
                    if score > best_score:
                        best_score = score
                        best_r = r
        if best_r and best_score >= 0.72:
            print(f"AnimeUnity ✓ [title-match score={best_score:.2f}] anilist={anilist_id} -> AU slug={best_r.get('slug')}")
            return best_r
        return None

    if not sub_record: sub_record = fuzzy_match(False)
    if not dub_record: dub_record = fuzzy_match(True)

    return sub_record, dub_record

def au_get_episodes(au_anime_id: int) -> list:
    """Get episode list from AnimeUnity for an anime."""
    client = get_au_client()
    res = client.get(f"{AU_BASE}/info_api/{au_anime_id}/0")
    data = res.json()
    episode_count = data.get("episodes_count", 0)
    episodes = []
    batch = 120
    current = 0
    while current < episode_count:
        end = min(current + batch, episode_count)
        r = client.get(f"{AU_BASE}/info_api/{au_anime_id}/0",
                       params={"start_range": current + 1, "end_range": end})
        batch_data = r.json()
        for ep in batch_data.get("episodes", []):
            episodes.append({"number": ep.get("number", current + 1), "au_id": ep["id"]})
        current = end
    return episodes

def au_get_stream_url(episode_id: int) -> str:
    """Fetch the live HLS stream URL for an AnimeUnity episode."""
    client = get_au_client()
    # Step 1: get embed URL
    res = client.get(f"{AU_BASE}/embed-url/{episode_id}")
    embed_url = res.text.strip().strip('"')
    if not embed_url.startswith("http"):
        raise Exception(f"Invalid embed URL: {embed_url!r}")
    # Step 2: fetch embed HTML
    res2 = client.get(embed_url, headers={"Referer": AU_BASE})
    html = res2.text
    # Step 3: extract masterPlaylist token/expires
    token, expires = "", ""
    m_master = re.search(r'window\.masterPlaylist\s*=\s*\{([\s\S]*?)\}', html)
    if m_master:
        m_tok = re.search(r'["\']?token["\']?\s*:\s*["\']([^"\' ]+)["\']', m_master.group(1))
        m_exp = re.search(r'["\']?expires["\']?\s*:\s*["\']([^"\' ]+)["\']', m_master.group(1))
        if m_tok: token = m_tok.group(1)
        if m_exp: expires = m_exp.group(1)
    # Step 4: extract streams
    m_streams = re.search(r'window\.streams\s*=\s*(\[[\s\S]*?\]);', html)
    if not m_streams:
        raise Exception("streams not found in embed HTML")
    streams_raw = m_streams.group(1).replace("\\u0026", "&").replace("\\u003d", "=")
    streams = json.loads(streams_raw)
    # Prefer Server1, fallback to first
    stream = next((s for s in streams if s.get("name") == "Server1"), streams[0] if streams else None)
    if not stream:
        raise Exception("No streams available")
    playlist_url = stream["url"].replace("\u0026", "&").replace("\u003d", "=")
    final = f"{playlist_url}&token={token}&expires={expires}&h=1"
    print(f"Stream URL: {final[:80]}...")
    return final


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
        "id": id,
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

@app.get("/api/stream")
def get_episode_stream(ep_id: int = Query(..., description="AnimeUnity episode ID")):
    """Fetch the live HLS stream URL for an AnimeUnity episode (called on demand when user clicks)."""
    try:
        url = au_get_stream_url(ep_id)
        return {"url": url}
    except Exception as e:
        print("Stream fetch error:", e)
        raise HTTPException(status_code=502, detail=f"Could not fetch stream: {e}")

@app.get("/api/episodes")
def get_anime_episodes(
    title: str = Query(..., description="The anime romaji title"),
    en: str = Query(None, description="The anime English title (fallback)"),
    anilist_id: int = Query(None, description="AniList anime ID"),
    c: int = Query(None, description="Total episodes count from anilist")
):
    # ── 1. Try AnimeUnity first (exact AniList ID match, no fuzzy nonsense) ──
    if anilist_id:
        try:
            hints = au_build_hints(title, en)
            au_sub, au_dub = au_search_both(anilist_id, hints)
            
            eps_data = []
            ita_data = []
            
            if au_sub:
                eps_data = au_get_episodes(au_sub["id"])
                
            if au_dub:
                try:
                    ita_data = au_get_episodes(au_dub["id"])
                except Exception as dub_e:
                    print("AU dub episode fetch failed:", dub_e)
                    
            if eps_data or ita_data:
                return {"data": eps_data, "ita_data": ita_data, "source": "animeunity"}
                
        except Exception as au_e:
            print("AnimeUnity failed, falling back to AnimeWorld:", au_e)

    # If AnimeUnity fails, return empty
    target_c = c if c is not None else 1
    max_eps = max(1, min(target_c, 5000))
    html_content = "<html><body style='background:#111;color:#a855f7;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;text-align:center'><h2>Episodio in Arrivo / Stream Non Trovato</h2></body></html>"
    import urllib.parse
    data_uri = "data:text/html;charset=utf-8," + urllib.parse.quote(html_content)
    return {"data": [{"number": str(i+1), "link": data_uri} for i in range(max_eps)], "ita_data": [], "source": "fallback"}


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
