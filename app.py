from flask import Flask, request, jsonify, send_from_directory
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

app = Flask(__name__)

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id='CLIENT_ID_REMOVED_FOR_GIT',
                                                          client_secret='CLIENT_SECRET_REMOVED_FOR_GIT'))

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
    return jsonify([])

@app.route('/generate_playlist', methods=['POST'])
@app.route('/generate_playlist', methods=['POST'])
def generate_playlist():
    data = request.json
    song_ids = []
    for song in data.get('songs', []):
        search_result = sp.search(q=f'{song}', type='track')
        if search_result['tracks']['items']:
            song_ids.append(search_result['tracks']['items'][0]['id'])
    
    # Get recommendations based on the seed tracks
    recommendations = sp.recommendations(seed_tracks=song_ids, limit=int(data.get('playlistSize', 10)))

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

if __name__ == '__main__':
    app.run(debug=True)