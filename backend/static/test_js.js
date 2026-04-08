const state = { 
    catalog: { 
        "Nuove Uscite": [{name: "A", image: "B", link: "C"}], 
        "Azione": [{name: "X", image: "B", link: "C"}],
        "Fantasy": [{name: "Y", image: "B", link: "C"}]
    }, 
    filterGenre: "ALL", 
    filterSort: "DEFAULT", 
    continueWatching: [{name: "CW1", image: "IMG", progress: 5}] 
};

function renderCardsTemplate(animes, isContinueWatching = false) {
    if (!animes || !animes[Symbol.iterator]) return '';
    let sorted = [...animes];
    if (!isContinueWatching) {
        if (state.filterGenre !== "ALL") {
            sorted = sorted.filter(a => a.categories && a.categories.some(c => c.name.toLowerCase() === state.filterGenre.toLowerCase()));
        }
        if (state.filterSort === "DESC") {
            sorted.sort((a,b) => (b.malVote || 0) - (a.malVote || 0));
        } else if (state.filterSort === "ASC") {
            sorted.sort((a,b) => (a.malVote || 0) - (b.malVote || 0));
        }
    }
    
    if (sorted.length === 0) return '';
    return sorted.map(anime => `<card>${anime.name}</card>`).join("");
}

let contentHtml = "";

if (state.continueWatching && state.continueWatching.length > 0 && state.filterGenre === "ALL") {
    const cards = renderCardsTemplate(state.continueWatching, true);
    if (cards) contentHtml += `[[CONTINUE:${cards}]]\n`;
}

Object.keys(state.catalog).forEach(category => {
    if (state.filterGenre !== "ALL" && category !== "Nuove Uscite" && category.toLowerCase() !== state.filterGenre.toLowerCase()) {
        return;
    }
    const cards = renderCardsTemplate(state.catalog[category]);
    if (cards) contentHtml += `[[CAT-${category}:${cards}]]\n`;
});

console.log(contentHtml);
