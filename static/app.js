// Application State
const state = {
    catalog: {}, // Category -> Anime list
    searchResults: [],
    genres: new Set(),
    isSearching: false,
    filterGenre: "ALL",
    filterSort: "DEFAULT",
    isLoading: false,
    // Autocomplete
    autocompleteTimer: null,
    // Episode audio mode: 'sub' or 'ita'
    currentSubEps: [],
    currentItaEps: [],
    audioMode: 'sub',
    currentEpNumber: null,  // episode number currently playing
    episodeSource: 'animeunity'
};

// Router singleton
const router = {
    navigate: (path) => {
        window.history.pushState(null, '', path);
        handleRoute();
    }
};
window.addEventListener('popstate', handleRoute);
window.router = router;

// DOM Elements
const appDiv = document.getElementById('app');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');

// Initial Load
async function fetchCatalog() {
    state.isLoading = true;
    renderLoader();
    try {
        const res = await fetch('/api/home');
        const data = await res.json();
        
        state.catalog = data.data || {};
        
        state.genres.clear();
        Object.values(state.catalog).forEach(list => {
            list.forEach(anime => {
                if (anime.categories) {
                    anime.categories.forEach(cat => state.genres.add(cat.name));
                }
            });
        });
        
    } catch (e) {
        console.error("Error fetching home:", e);
        appDiv.innerHTML = `<div class="loader">Errore di comunicazione col server.</div>`;
    }
    state.isLoading = false;
    renderHome();
}

async function searchAnime(keyword) {
    if (!keyword.trim()) {
        state.isSearching = false;
        renderHome();
        return;
    }
    state.isSearching = true;
    renderLoader();
    try {
        const res = await fetch(`/api/search?keyword=${encodeURIComponent(keyword)}`);
        const data = await res.json();
        state.searchResults = data.data;
    } catch(e) {
        state.searchResults = [];
    }
    renderHome();
}

function handleRoute() {
    const path = window.location.pathname;
    
    if (path.startsWith('/play/')) {
        const id = path.split('/').pop();
        renderWatchPage(id);
    } else {
        if (Object.keys(state.catalog).length === 0) fetchCatalog();
        else renderHome();
    }
}

// ------------------------ RENDERING ------------------------

function renderLoader() {
    appDiv.innerHTML = `<div class="loader">Caricamento in corso...</div>`;
}

function renderCardsTemplate(animes) {
    let sorted = [...animes];
    if (state.filterGenre !== "ALL") {
        sorted = sorted.filter(a => a.categories && a.categories.some(c => c.name.toLowerCase() === state.filterGenre.toLowerCase()));
    }
    if (state.filterSort === "DESC") {
        sorted.sort((a,b) => (b.malVote || 0) - (a.malVote || 0));
    } else if (state.filterSort === "ASC") {
        sorted.sort((a,b) => (a.malVote || 0) - (b.malVote || 0));
    }
    
    if (sorted.length === 0) return '';

    return sorted.map(anime => `
        <div class="anime-card" onclick="router.navigate('${anime.link}')">
            <img class="anime-card-img" src="${anime.image}" alt="${anime.name}" loading="lazy">
            <div class="anime-card-overlay">
                <div class="anime-title">${anime.name}</div>
                <div class="anime-vote">★ ${anime.malVote || '?'} / 10</div>
            </div>
        </div>
    `).join("");
}

function renderHome() {
    let genreOptions = `<option value="ALL">Tutti i generi</option>`;
    Array.from(state.genres).sort().forEach(g => {
        genreOptions += `<option value="${g}" ${state.filterGenre === g ? 'selected' : ''}>${g}</option>`;
    });

    let contentHtml = "";

    if (state.isSearching) {
        const cards = renderCardsTemplate(state.searchResults);
        contentHtml = cards ? `<div class="anime-grid">${cards}</div>` : `<p>Nessun risultato trovato.</p>`;
    } else {
        // Render categorized horizontal rows (Netflix style)
        Object.keys(state.catalog).forEach(category => {
            // Optional: Skip genre specific rows if a different genre is explicitly selected
            if (state.filterGenre !== "ALL" && category !== "Nuove Uscite" && category.toLowerCase() !== state.filterGenre.toLowerCase()) {
                return;
            }
            const cards = renderCardsTemplate(state.catalog[category]);
            if (cards) {
                contentHtml += `
                    <div class="anime-row-container">
                        <h2 class="anime-row-title">${category}</h2>
                        <div class="anime-row">
                            ${cards}
                        </div>
                    </div>
                `;
            }
        });
    }

    appDiv.innerHTML = `
        <div class="filters-section">
            <select id="genreFilter" onchange="applyFilters()">
                ${genreOptions}
            </select>
            <select id="ratingFilter" onchange="applyFilters()">
                <option value="DEFAULT" ${state.filterSort === 'DEFAULT' ? 'selected' : ''}>Ordina per Voto</option>
                <option value="DESC" ${state.filterSort === 'DESC' ? 'selected' : ''}>Voto (Più Alto)</option>
                <option value="ASC" ${state.filterSort === 'ASC' ? 'selected' : ''}>Voto (Più Basso)</option>
            </select>
        </div>
        ${contentHtml}
    `;
}

// Search Binding
searchBtn.addEventListener('click', () => {
    closeAutocomplete();
    searchAnime(searchInput.value);
});
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') { closeAutocomplete(); searchAnime(searchInput.value); }
});
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAutocomplete();
});

// Autocomplete with debounce
searchInput.addEventListener('input', () => {
    clearTimeout(state.autocompleteTimer);
    const query = searchInput.value.trim();
    if (!query || query.length < 2) { closeAutocomplete(); return; }
    state.autocompleteTimer = setTimeout(() => showAutocomplete(query), 200);
});

document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-container')) closeAutocomplete();
});

function closeAutocomplete() {
    const list = document.getElementById('autocompleteList');
    if (list) list.innerHTML = '';
    const list2 = document.getElementById('autocompleteList');
    if (list2) list2.style.display = 'none';
}

async function showAutocomplete(query) {
    const list = document.getElementById('autocompleteList');
    if (!list) return;

    // Build candidates from in-memory catalog first (instant)
    const lq = query.toLowerCase();
    const seen = new Set();
    const candidates = [];
    Object.values(state.catalog).forEach(row => {
        row.forEach(anime => {
            if (!seen.has(anime.link) && anime.name.toLowerCase().includes(lq)) {
                seen.add(anime.link);
                candidates.push(anime);
            }
        });
    });
    
    // If few local matches, also hit the API
    if (candidates.length < 4) {
        try {
            const res = await fetch(`/api/search?keyword=${encodeURIComponent(query)}`);
            const data = await res.json();
            (data.data || []).forEach(anime => {
                if (!seen.has(anime.link)) {
                    seen.add(anime.link);
                    candidates.push(anime);
                }
            });
        } catch (_) {}
    }

    const top = candidates.slice(0, 7);
    if (top.length === 0) { list.style.display = 'none'; return; }

    list.style.display = 'block';
    list.innerHTML = '';
    top.forEach(a => {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.innerHTML = `
            <img src="${a.image}" alt="" class="autocomplete-img" onerror="this.style.display='none'">
            <div class="autocomplete-info">
                <span class="autocomplete-name">${a.name}</span>
                <span class="autocomplete-vote">★ ${a.malVote || '?'}</span>
            </div>
        `;
        // Use mousedown instead of click to fire before the document blur handler closes the list
        item.addEventListener('mousedown', (e) => {
            e.preventDefault(); // prevent input blur
            closeAutocomplete();
            router.navigate(a.link);
        });
        list.appendChild(item);
    });
}

window.applyFilters = () => {
    state.filterGenre = document.getElementById('genreFilter').value;
    state.filterSort = document.getElementById('ratingFilter').value;
    renderHome();
};

// ---------------------- WATCH PAGE -------------------------

async function renderWatchPage(id) {
    renderLoader();
    try {
        const detRes = await fetch(`/api/anime?id=${id}`);
        if (!detRes.ok) throw new Error("API responded with an error");
        const data = await detRes.json();
        const info = data.info || {};
        const seasons = data.seasons || [];
        let seasonsHtml = "";
        if (seasons.length > 0) {
            seasonsHtml = `
            <div class="season-selector" style="margin-top: 15px;">
                <label style="font-size: 0.8em; opacity: 0.7; margin-bottom: 5px; display: block;">Serie Collegate (Stagioni / Film):</label>
                <select onchange="router.navigate('/play/' + this.value)" style="background:rgba(255,255,255,0.1); color:#fff; padding: 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); width: 100%; cursor: pointer; outline:none; font-family:inherit;">
                    <option value="" disabled selected>Cambia stagione...</option>
                    ${seasons.map(s => `<option value="${s.id}">${s.title} (${s.relation})</option>`).join('')}
                </select>
            </div>
            `;
        }
        
        appDiv.innerHTML = `
            <div class="watch-container">
                <div class="watch-hero">
                    <img src="${data.cover}" class="watch-hero-bg">
                    <div class="watch-hero-content">
                        <div class="watch-cover-col">
                            <img src="${data.poster}" class="watch-cover">
                            <div id="audioToggleBox" class="audio-toggle" style="margin-top:12px;"></div>
                        </div>
                        <div class="watch-info">
                            <h1>${data.name}</h1>
                            <div class="watch-desc">${data.trama}</div>
                            <div class="watch-meta">
                                <span>${info['Stato'] || ''}</span>
                                <span>Episodi: ${info['Episodi'] || '?'}</span>
                                <span>Voto: ★ ${info['Voto'] || '?'}</span>
                                <div style="margin-top: 10px; font-size: 0.9em; opacity: 0.8;">${info['Generi'] || ''}</div>
                                ${seasonsHtml}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div id="playerBox" class="player-container">
                    <iframe id="videoIframe" allowfullscreen></iframe>
                </div>

                <div class="episodes-section">
                    <h2>Episodi Streaming</h2>
                    <div id="episodesGrid" class="episodes-grid">
                         <div class="loader">Ricerca streaming in corso...</div>
                    </div>
                </div>
            </div>
        `;
        
        // Fetch episodes — pass AniList ID for AnimeUnity direct lookup
        fetchEpisodes(data.romajiTitle || data.name, info['Episodi'], data.englishTitle, data.id);
        
    } catch(e) {
        console.error("Watch load failed", e);
        appDiv.innerHTML = `<div class="loader">Impossibile trovare l'anime su Anilist.</div>`;
    }
}

async function fetchEpisodes(title, countStr, englishTitle, anilistId) {
    try {
        let qs = `title=${encodeURIComponent(title)}`;
        if (englishTitle) qs += `&en=${encodeURIComponent(englishTitle)}`;
        if (anilistId) qs += `&anilist_id=${anilistId}`;
        if (countStr && countStr !== '?' && !isNaN(countStr)) qs += `&c=${countStr}`;

        const res = await fetch(`/api/episodes?${qs}`);
        const epData = await res.json();
        
        const grid = document.getElementById('episodesGrid');
        if (!grid) return;

        state.currentSubEps = epData.data || [];
        state.currentItaEps = epData.ita_data || [];
        state.episodeSource = 'animeunity';
        state.audioMode = 'sub';

        if (state.currentSubEps.length === 0) {
            grid.innerHTML = '<p>Nessun episodio trovato sul server stream.</p>';
            return;
        }

        renderEpisodeGrid();

        // Update section heading with source badge
        const heading = document.querySelector('.episodes-section h2');
        if (heading) {
            heading.innerHTML = `Episodi Streaming <span style="font-size:0.55em;background:linear-gradient(135deg,#7b2cbf,#a855f7);padding:3px 10px;border-radius:20px;margin-left:12px;vertical-align:middle;">AnimeUnity ✨</span>`;
        }

    } catch(e) {
        console.error("Episode fetch failed", e);
        const grid = document.getElementById('episodesGrid');
        if (grid) grid.innerHTML = '<p>Lo streaming non è attualmente disponibile per questo titolo.</p>';
    }
}

function renderEpisodeGrid() {
    const grid = document.getElementById('episodesGrid');
    if (!grid) return;
    const eps = state.audioMode === 'ita' ? state.currentItaEps : state.currentSubEps;
    const hasIta = state.currentItaEps.length > 0;

    // Inject toggle buttons under the poster
    const toggleBox = document.getElementById('audioToggleBox');
    if (toggleBox) {
        toggleBox.innerHTML = hasIta ? `
            <button class="audio-btn ${state.audioMode === 'sub' ? 'active' : ''}" onclick="window.switchAudioMode('sub')">&#127244; Sub ITA</button>
            <button class="audio-btn ${state.audioMode === 'ita' ? 'active' : ''}" onclick="window.switchAudioMode('ita')">&#127470;&#127481; Doppiato</button>
        ` : '';
    }

    // Build episode buttons
    grid.innerHTML = eps.map(ep => {
        return `<div class="episode-btn" data-epnum="${ep.number}" onclick="window.playEpisode(${ep.au_id}, this)">Ep. ${ep.number}</div>`;
    }).join('');
}

window.switchAudioMode = async (mode) => {
    if (state.audioMode === mode) return;
    state.audioMode = mode;
    renderEpisodeGrid();

    // Auto-replay the same episode number in the new language
    if (state.currentEpNumber == null) return;
    const eps = mode === 'ita' ? state.currentItaEps : state.currentSubEps;
    if (!eps.length) return;

    // Yield to let DOM update finish
    await new Promise(r => setTimeout(r, 0));

    // Find the episode with the matching number
    const ep = eps.find(e => String(e.number) === String(state.currentEpNumber)) || eps[0];
    // Find and highlight the button by data-epnum
    const btn = [...document.querySelectorAll('.episode-btn')]
        .find(el => el.dataset.epnum === String(ep.number));
    if (!btn) return;
    if (ep.au_id) {
        await window.playEpisode(ep.au_id, btn);
    }
};

// Fetch stream URL on-demand, then play via HLS.js
window.playEpisode = async (auEpId, btnElement) => {
    document.querySelectorAll('.episode-btn').forEach(el => el.classList.remove('active'));
    btnElement.classList.add('active');
    btnElement.textContent = '⏳ Carico...';

    const playerBox = document.getElementById('playerBox');
    playerBox.classList.add('active');
    playerBox.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#000;color:#a855f7;font-size:1.2em">⏳ Caricamento stream...</div>`;
    playerBox.scrollIntoView({ behavior: 'smooth', block: 'center' });

    try {
        const res = await fetch(`/api/stream?ep_id=${auEpId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const { url } = await res.json();
        const epNum = btnElement.dataset.epnum || auEpId;
        state.currentEpNumber = epNum;  // track for language switch
        btnElement.textContent = `Ep. ${epNum}`;
        btnElement.classList.add('active');
        playHLS(url, playerBox);
    } catch(e) {
        console.error('Stream fetch error', e);
        playerBox.innerHTML = `<div style="color:red;text-align:center;padding:2rem">Errore caricamento stream: ${e.message}</div>`;
        btnElement.textContent = btnElement.textContent.replace('⏳ Carico...', 'Ep.');
    }
};

// HLS.js player
function playHLS(url, playerBox) {
    playerBox.innerHTML = `<video id="videoPlayer" autoplay controls playsinline style="width:100%;height:100%;background:#000"></video>`;
    const video = document.getElementById('videoPlayer');
    if (!video) return;

    if (typeof Hls === 'undefined') {
        // Fallback: some browsers support HLS natively (Safari)
        video.src = url;
        video.play().catch(() => {});
        return;
    }

    if (Hls.isSupported()) {
        const hls = new Hls({ enableWorker: false, maxBufferLength: 30 });
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
        hls.on(Hls.Events.ERROR, (evt, data) => {
            if (data.fatal) {
                console.error('HLS fatal error', data);
                playerBox.innerHTML = `<div style="color:red;text-align:center;padding:2rem">Errore riproduzione HLS: ${data.type}</div>`;
            }
        });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = url;
        video.play().catch(() => {});
    } else {
        playerBox.innerHTML = `<div style="color:#a855f7;text-align:center;padding:2rem">Il tuo browser non supporta lo streaming HLS.</div>`;
    }
}

// Start
handleRoute();
