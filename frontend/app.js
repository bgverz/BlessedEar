let selectedSongs = [];
let playlist = [];  // Global variable to store the generated playlist

document.getElementById('search-input').addEventListener('input', async function (e) {
    const query = e.target.value;
    const autocomplete = document.getElementById('autocomplete');

    if (query.length > 0) {
        try {
            const results = await searchSongs(query);
            if (results.length > 0) {
                let autocompleteHtml = '<ul>';
                results.forEach(track => {
                    autocompleteHtml += `
                        <li>
                            <img src="${track.album_cover}" alt="${track.name}" width="40">
                            ${track.name} - ${track.artist}
                            <button onclick="addSong('${track.name}', '${track.artist}', '${track.album_cover}', '${track.id}')">+</button>
                        </li>`;
                });
                autocompleteHtml += '</ul>';
                autocomplete.innerHTML = autocompleteHtml;
                autocomplete.style.display = 'block';
            } else {
                autocomplete.innerHTML = '';
                autocomplete.style.display = 'none';
            }
        } catch (error) {
            console.error('Error fetching search results:', error);
        }
    } else {
        autocomplete.innerHTML = '';
        autocomplete.style.display = 'none';
    }
});

// Handle dropdown showing/hiding on focus/blur
document.getElementById('search-input').addEventListener('focus', function () {
    document.getElementById('autocomplete').style.display = 'block';
});

document.getElementById('search-input').addEventListener('blur', function () {
    setTimeout(function () {
        document.getElementById('autocomplete').style.display = 'none';
    }, 200);
});

async function searchSongs(query) {
    try {
        const response = await fetch(`http://127.0.0.1:5000/search_song?q=${query}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching search results:', error);
        return [];
    }
}

function addSong(name, artist, album_cover, id) {
    const song = { name, artist, album_cover, id };
    if (!selectedSongs.some(s => s.name === name && s.artist === artist)) {
        selectedSongs.push(song);
        updateSelectedSongs();
    }
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

function removeSong(name, artist) {
    selectedSongs = selectedSongs.filter(song => song.name !== name || song.artist !== artist);
    updateSelectedSongs();
}

document.getElementById('playlist-form').addEventListener('submit', async function (e) {
    e.preventDefault();

    const playlistSize = document.getElementById('playlist-size').value;
    const playlistContainer = document.getElementById('generated-playlist');  // Ensure this element is referenced correctly

    try {
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
        playlist = data.playlist;  // Store generated playlist globally

        let playlistHtml = '<h2>Your Playlist</h2><ul>';
        playlist.forEach(song => {
            playlistHtml += `
            <li style="display: flex; align-items: center;">
                <img src="${song.album_cover}" alt="${song.name}" width="50" style="margin-right: 10px;">
                ${song.name} - ${song.artist}
            </li>`;
        });
        playlistHtml += '</ul>';
        playlistContainer.innerHTML = playlistHtml;  // Ensure the correct container is used

    } catch (error) {
        console.error('Error generating playlist:', error);
    }
});

async function createSpotifyPlaylist() {
    if (playlist.length === 0) {
        alert('No songs in playlist!');
        return;
    }

    const trackIds = playlist.map(song => song.id);
    console.log('Track IDs for Spotify Playlist:', trackIds);  // Debugging the track IDs

    try {
        const createResponse = await fetch('http://127.0.0.1:5000/create_spotify_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                song_ids: trackIds
            })
        });

        const createData = await createResponse.json();
        console.log('Spotify Playlist Response:', createData);  // Debugging the backend response

        if (createData.playlist_url) {
            const spotifyLink = document.createElement('a');
            spotifyLink.href = createData.playlist_url;
            spotifyLink.target = '_blank';
            spotifyLink.innerText = 'View Playlist on Spotify';
            document.getElementById('generated-playlist').appendChild(spotifyLink);
        } else {
            console.error('Error: Playlist URL not found in response.');
        }
    } catch (error) {
        console.error('Error creating Spotify playlist:', error);
    }
}