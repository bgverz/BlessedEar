from flask import Flask, request, jsonify, send_from_directory
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

app = Flask(__name__)

# Spotify API credentials
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id='CLIENT_ID_HERE',
                                               client_secret='CLIENT_SECRET_HERE',
                                               redirect_uri='http://127.0.0.1:5000/callback',
                                               scope='playlist-modify-public'))

@app.route('/')
def home():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('frontend', filename)

@app.route('/search_song', methods=['GET'])
def search_song():
    query = request.args.get('q', '')
    if query:
        try:
            results = sp.search(q=query, type='track', limit=5)
            tracks = []
            for item in results['tracks']['items']:
                track_info = {
                    'name': item['name'],
                    'artist': item['artists'][0]['name'],
                    'album_cover': item['album']['images'][0]['url'],
                    'id': item['id']
                }
                tracks.append(track_info)
            return jsonify(tracks)
        except Exception as e:
            print(f"Error with Spotify search: {str(e)}")
            return jsonify({"error": "Spotify search failed"}), 500
    return jsonify([])

@app.route('/generate_playlist', methods=['POST'])
def generate_playlist():
    data = request.json
    song_ids = []

    # Search for each song to get the track IDs
    for song in data.get('songs', []):
        search_result = sp.search(q=f'{song}', type='track')
        if search_result['tracks']['items']:
            song_ids.append(search_result['tracks']['items'][0]['id'])

    # If song_ids is empty, return an error
    if not song_ids:
        return jsonify({"error": "No valid seed tracks found"}), 400

    # Get recommendations based on the selected songs
    try:
        recommendations = sp.recommendations(seed_tracks=song_ids, limit=int(data.get('playlistSize', 10)))
    except spotipy.exceptions.SpotifyException as e:
        print(f"Error fetching recommendations: {e}")
        return jsonify({"error": "Failed to generate recommendations"}), 500

    # Build the playlist
    playlist = []
    for track in recommendations['tracks']:
        track_info = {
            'name': track['name'],
            'artist': track['artists'][0]['name'],
            'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else '',
            'id': track['id']
        }
        playlist.append(track_info)

    return jsonify({"playlist": playlist})

@app.route('/create_spotify_playlist', methods=['POST'])
def create_spotify_playlist():
    data = request.json
    print('Data received for playlist:', data)  # Debugging

    playlist_name = data.get('name', 'My BlessedEar Playlist')
    song_ids = data.get('song_ids', [])
    print('Song IDs:', song_ids)  # Debugging

    # Create the playlist and add tracks
    try:
        playlist = sp.user_playlist_create(sp.current_user()['id'], playlist_name)
        print('Created playlist:', playlist)  # Debugging

        sp.user_playlist_add_tracks(sp.current_user()['id'], playlist['id'], song_ids)
        return jsonify({"message": "Playlist created successfully", "playlist_url": playlist['external_urls']['spotify']})

    except Exception as e:
        print(f'Error creating playlist: {e}')
        return jsonify({"error": "Failed to create playlist"}), 500
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
