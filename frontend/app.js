let selectedSongs = [];

async function searchSongs(query) {
    const response = await fetch(`http://127.0.0.1:5000/search_song?q=${query}`);
    const results = await response.json();
    return results;
}

document.getElementById('search-input').addEventListener('input', async function(e) {
    const query = e.target.value;
    const autocomplete = document.getElementById('autocomplete');

    if (query.length > 0) {
        const results = await searchSongs(query);
        let autocompleteHtml = '<ul>';
        results.forEach(track => {
            autocompleteHtml += `
                <li>
                    <img src="${track.album_cover}" alt="${track.name}" width="40">
                    ${track.name} - ${track.artist}
                    <button onclick="addSong('${track.name}', '${track.artist}', '${track.album_cover}')">+</button>
                </li>`;
        });
        autocompleteHtml += '</ul>';
        autocomplete.innerHTML = autocompleteHtml;
        console.log('Dropdown Content:', autocompleteHtml); // Debugging line
        autocomplete.style.display = 'block'; // Ensure dropdown is shown
    } else {
        autocomplete.innerHTML = '';
        autocomplete.style.display = 'none'; // Hide dropdown if no input
    }
});

function addSong(name, artist, album_cover) {
    const song = { name, artist, album_cover };
    if (!selectedSongs.some(s => s.name === name && s.artist === artist)) {
        selectedSongs.push(song);
        updateSelectedSongs();
    }
}

function removeSong(name, artist) {
    selectedSongs = selectedSongs.filter(song => song.name !== name || song.artist !== artist);
    updateSelectedSongs();
}

function updateSelectedSongs() {
    const selectedSongsList = document.getElementById('selected-songs');
    selectedSongsList.innerHTML = '';
    selectedSongs.forEach(song => {
        const li = document.createElement('li');
        li.innerHTML = `
            <img src="${song.album_cover}" alt="${song.name}" width="50">
            ${song.name} - ${song.artist}
            <button onclick="removeSong('${song.name}', '${song.artist}')">-</button>`;
        selectedSongsList.appendChild(li);
    });
}

document.getElementById('playlist-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const playlistSize = document.getElementById('playlist-size').value;

    const response = await fetch('http://127.0.0.1:5000/generate_playlist', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            songs: selectedSongs.map(song => `${song.name} - ${song.artist}`),
            playlistSize: playlistSize
        })
    });

    const data = await response.json();
    const playlist = data.playlist;
    
    let playlistHtml = '<h2>Your Playlist</h2><ul>';
    playlist.forEach(song => {
        playlistHtml += `
        <li style="display: flex; align-items: center;">
            <img src="${song.album_cover}" alt="${song.name}" width="50" style="margin-right: 10px;">
            ${song.name} - ${song.artist}
        </li>`;
    });
    playlistHtml += '</ul>';
    document.getElementById('playlist').innerHTML = playlistHtml;
});

// Hover functionality for the autocomplete dropdown
const searchInput = document.getElementById('search-input');
const autocomplete = document.getElementById('autocomplete');

// Show the dropdown when hovering over the search input
searchInput.addEventListener('mouseenter', function() {
    autocomplete.style.display = 'block';
});

// Keep the dropdown visible when hovering over it
autocomplete.addEventListener('mouseenter', function() {
    autocomplete.style.display = 'block';
});

// Hide the dropdown when the mouse leaves both the input and the dropdown
searchInput.addEventListener('mouseleave', function() {
    setTimeout(function() {
        if (!autocomplete.matches(':hover')) {
            autocomplete.style.display = 'none';
        }
    }, 100); // Delay to ensure smooth transition
});

autocomplete.addEventListener('mouseleave', function() {
    autocomplete.style.display = 'none';
});
