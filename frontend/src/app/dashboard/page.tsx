'use client'

import React, { useState, useEffect } from 'react';
import { Music, BarChart3, Sparkles, PlayCircle, Heart, TrendingUp, Loader2, Clock, Star, ExternalLink, Trash2, Plus, Download, Calendar, Hash, Save } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface UserProfile {
  user_id: string;
  avg_features: {
    danceability: number;
    energy: number;
    valence: number;
    speechiness: number;
    acousticness: number;
    instrumentalness: number;
    liveness: number;
    tempo: number;
  };
  total_tracks_analyzed: number;
}

interface RecommendationTrack {
  id: string;
  name: string;
  artists: string[];
  recommendation_reason: string;
  similarity_score: number;
  popularity?: number;
  preview_url?: string;
  album?: string;
  album_image_url?: string | null;
  album_images?: Array<{url: string; width: number; height: number}>;
  external_urls?: {spotify?: string};
}

interface TopTrack {
  id: string;
  name: string;
  artists: { name: string }[];
  album: {
    name: string;
    images?: Array<{ url: string; width: number; height: number }>;
  };
  album_images?: Array<{ url: string; width: number; height: number }>;
  album_image_url?: string | null;
  popularity: number;
  preview_url?: string;
  external_urls?: { spotify?: string };
}

interface TasteProfileTrait {
  name: string;
  value: number;
  level: 'Low' | 'Medium' | 'High';
}

interface TasteProfile {
  spotify_id: string;
  archetype: string;
  top_genres: string[];
  traits: TasteProfileTrait[];
  signals: {
    discovery_score: number;
    artist_loyalty: number;
    mainstream_index: number;
    deep_cut_ratio: number;
  };
}

interface ListeningInsightsPayload {
  spotify_id: string;
  time_range: 'short_term' | 'medium_term' | 'long_term';
  archetype: string;
  listening_insights: {
    discovery_score: number;
    artist_loyalty: number;
    mainstream_index: number;
  };
  sound_profile: {
    genre_breakdown: Array<{ genre: string; percentage: number }>;
  };
  hidden_gems: Array<{
    id: string;
    name: string;
    artists: string[];
    popularity: number;
    album_image_url?: string | null;
  }>;
}

interface SavedPlaylist {
  id: number;
  name: string;
  description?: string;
  track_count: number;
  mood?: string;
  generation_type: string;
  is_exported: boolean;
  spotify_playlist_id?: string;
  created_at: string;
}

interface GeneratedPlaylistTrack {
  track_id: string;
  name: string;
  artist: string;
  artists?: string[];
  album?: string;
  album_cover_url?: string | null;
  album_images?: Array<{ url: string; width?: number; height?: number }>;
  spotify_url: string;
}

interface DiscoverGenreCard {
  genre: string;
  description: string;
  sample_artists: string[];
}

interface DiscoverArtistCard {
  id: string;
  name: string;
  genres: string[];
  image_url?: string | null;
  popularity: number;
  reason: string;
  external_urls?: { spotify?: string };
}

interface DiscoverArtistDetail {
  artist: DiscoverArtistCard;
  top_tracks: RecommendationTrack[];
  similar_artists: DiscoverArtistCard[];
}

interface DiscoverExplorerPayload {
  outside_your_bubble: DiscoverGenreCard[];
  artists_you_should_know: DiscoverArtistCard[];
  underground_radar: RecommendationTrack[];
  trending_outside_your_taste: RecommendationTrack[];
}

async function getCurrentUser(token: string) {
  const response = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return response.json();
}

async function getUserProfile(token: string) {
  const response = await fetch(`${API_BASE}/api/recommendations/profile`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return response.json();
}

async function generateRecommendations(token: string, options: any = {}) {
  const response = await fetch(`${API_BASE}/api/recommendations/generate`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ limit: 20, ...options }),
  });
  const data = await response.json();
  return data.tracks || [];
}

async function fetchTasteProfile(token: string): Promise<TasteProfile | null> {
  try {
    const response = await fetch(`${API_BASE}/api/analytics/taste-profile`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchListeningInsights(
  token: string,
  timeRange: 'short_term' | 'medium_term' | 'long_term',
): Promise<ListeningInsightsPayload | null> {
  try {
    const response = await fetch(`${API_BASE}/api/analytics/listening-insights?time_range=${timeRange}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

const GlassCard = ({ children, className = "", ...props }) => (
  <div
    className={`backdrop-blur-md bg-white/10 border border-white/20 rounded-2xl p-6 shadow-lg ${className}`}
    {...props}
  >
    {children}
  </div>
);

function coerceGeneratedTracks(input: any[]): GeneratedPlaylistTrack[] {
  if (!Array.isArray(input)) return [];
  return input
    .map((track) => {
      if (!track || typeof track !== 'object') return null;
      if (typeof track.track_id !== 'string' || !track.track_id) return null;
      return {
        track_id: track.track_id,
        name: typeof track.name === 'string' && track.name ? track.name : 'Unknown Track',
        artist: typeof track.artist === 'string' && track.artist ? track.artist : 'Unknown Artist',
        artists: Array.isArray(track.artists) ? track.artists.filter((a: any) => typeof a === 'string') : undefined,
        album: typeof track.album === 'string' ? track.album : '',
        album_cover_url: typeof track.album_cover_url === 'string' ? track.album_cover_url : null,
        album_images: Array.isArray(track.album_images) ? track.album_images : [],
        spotify_url: typeof track.spotify_url === 'string' && track.spotify_url
          ? track.spotify_url
          : `https://open.spotify.com/track/${track.track_id}`,
      } as GeneratedPlaylistTrack;
    })
    .filter(Boolean) as GeneratedPlaylistTrack[];
}

const Sidebar = ({ activeTab, setActiveTab, userDisplayName }) => {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { id: 'discover', label: 'Discover', icon: Sparkles },
    { id: 'playlists', label: 'Playlists', icon: Music },
    { id: 'analytics', label: 'Analytics', icon: TrendingUp },
  ];

  return (
    <div className="fixed left-0 top-0 h-full w-64 backdrop-blur-xl bg-black/20 border-r border-white/10 p-6 z-10">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-green-600 rounded-lg flex items-center justify-center">
          <Music className="w-5 h-5 text-white" />
        </div>
        <h1 className="text-xl font-bold text-white">BlessedEar</h1>
      </div>

      {userDisplayName && (
        <div className="mb-6 p-3 bg-white/5 rounded-lg">
          <p className="text-sm text-gray-400">Welcome back,</p>
          <p className="text-white font-semibold">{userDisplayName}</p>
          <button
            onClick={async () => {
              const t = sessionStorage.getItem('access_token');

              sessionStorage.removeItem('access_token');

              if (t) {
                try {
                  const res = await fetch(`${API_BASE}/api/auth/switch`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${t}` },
                  });
                  const data = await res.json();
                  if (data.auth_url) {
                    window.location.href = data.auth_url;
                    return;
                  }
                } catch (_) { /* fall through to login page */ }
              }

              window.location.href = '/login';
            }}
            className="mt-2 w-full text-xs text-gray-400 hover:text-white py-1 px-2 rounded border border-gray-600 hover:border-gray-400 transition-colors"
          >
            Switch Account
          </button>
        </div>
      )}

      <nav className="space-y-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                activeTab === tab.id
                  ? 'bg-green-500 text-white shadow-lg shadow-green-500/25'
                  : 'text-gray-300 hover:bg-white/10 hover:text-white'
              }`}
            >
              <Icon className="w-5 h-5" />
              <span className="font-medium">{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
};

const TasteProfileCard = ({
  profile,
  isLoading,
  hasError,
  onRetry,
}: {
  profile: TasteProfile | null;
  isLoading: boolean;
  hasError: boolean;
  onRetry?: () => void;
}) => {
  if (isLoading) {
    return (
      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Your Taste Profile</h3>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-green-500" />
        </div>
      </GlassCard>
    );
  }

  if (hasError || !profile) {
    return (
      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Your Taste Profile</h3>
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <p className="text-sm text-gray-400 text-center">Taste profile is temporarily unavailable</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="text-xs text-green-400 hover:text-green-300 border border-green-500/30 px-3 py-1 rounded-lg transition-colors"
            >
              Retry
            </button>
          )}
        </div>
      </GlassCard>
    );
  }

  return (
    <GlassCard>
      <h3 className="text-lg font-semibold text-white mb-1">Your Taste Profile</h3>
      <p className="text-sm text-green-300 mb-3">{profile.archetype}</p>

      <div className="mb-3">
        <p className="text-xs text-gray-400 mb-1">Top Genres</p>
        <div className="flex flex-wrap gap-2">
          {profile.top_genres.slice(0, 6).map((genre) => (
            <span key={genre} className="text-xs bg-white/10 text-gray-200 px-2 py-1 rounded-full">
              {genre}
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {profile.traits.slice(0, 4).map((trait) => (
          <div key={trait.name}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-gray-300">{trait.name}</span>
              <span className="text-gray-400">{trait.level} · {trait.value}%</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-white/10">
              <div className="h-1.5 rounded-full bg-gradient-to-r from-green-500 to-cyan-400" style={{ width: `${trait.value}%` }} />
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
};

/** Pick the best-fit album image URL from track.album_images. */
const getAlbumImage = (track: RecommendationTrack, size: 'small' | 'medium' = 'small') => {
  if (track.album_image_url) return track.album_image_url;
  const imgs = track.album_images;
  if (!imgs || imgs.length === 0) return null;
  if (size === 'small') return imgs[2]?.url ?? imgs[1]?.url ?? imgs[0]?.url;
  return imgs[1]?.url ?? imgs[0]?.url;
};

const getTopTrackAlbumImage = (track: TopTrack): string | null => {
  if (track.album_image_url) return track.album_image_url;
  if (track.album_images?.length) return track.album_images[0]?.url ?? null;
  if (track.album?.images?.length) return track.album.images[0]?.url ?? null;
  return null;
};

/** List-row card used in Dashboard and playlist detail views. */
const RecommendationCard = ({ track, showSaveButton = false, onSave }: {
  track: RecommendationTrack;
  showSaveButton?: boolean;
  onSave?: () => void;
}) => {
  const albumImage = getAlbumImage(track, 'small');
  const spotifyUrl = track.external_urls?.spotify;

  return (
    <div className="group backdrop-blur-sm bg-white/5 border border-white/10 rounded-xl p-3 hover:bg-white/10 transition-all duration-200 cursor-pointer">
      <div className="flex items-center gap-3">
        {/* Album art with hover play overlay */}
        <div className="relative w-12 h-12 flex-shrink-0 rounded-lg overflow-hidden shadow-md">
          {albumImage ? (
            <>
              <img
                src={albumImage}
                alt={`${track.name} album cover`}
                className="w-full h-full object-cover transition-all duration-200 group-hover:scale-110 group-hover:brightness-75"
              />
              <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <PlayCircle className="w-5 h-5 text-white drop-shadow" />
              </div>
            </>
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-green-500/20 to-green-400/20 flex items-center justify-center group-hover:from-green-500/30 group-hover:to-green-400/30 transition-all duration-200">
              <Music className="w-6 h-6 text-green-500" />
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-white truncate">{track.name}</h4>
          <p className="text-sm text-gray-400 truncate">{track.artists.join(', ')}</p>
          <p className="text-xs text-green-400 truncate">{track.recommendation_reason}</p>
        </div>

        <div className="flex items-center gap-1.5">
          {showSaveButton && onSave && (
            <button
              onClick={onSave}
              className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center hover:bg-blue-500/30 transition-colors"
              title="Save to playlists"
            >
              <Save className="w-4 h-4 text-blue-400" />
            </button>
          )}
          {spotifyUrl && (
            <a
              href={spotifyUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:bg-green-500/20 transition-colors"
              title="Open in Spotify"
            >
              <ExternalLink className="w-4 h-4 text-gray-300 group-hover:text-green-400 transition-colors" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
};

/** Square album-art card used in the Discover grid. */
const AlbumTrackCard = ({ track }: { track: RecommendationTrack }) => {
  const albumImage = getAlbumImage(track, 'medium');
  const spotifyUrl = track.external_urls?.spotify;

  return (
    <div className="group flex flex-col transition-all duration-200 hover:-translate-y-1">
      {/* Album art container */}
      <div className="relative aspect-square rounded-xl overflow-hidden mb-3 shadow-lg shadow-black/30">
        {albumImage ? (
          <>
            {/* Blurred colour aura behind the art */}
            <div
              className="absolute inset-0 scale-110 blur-2xl opacity-30 z-0"
              style={{ backgroundImage: `url(${albumImage})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
            />
            <img
              src={albumImage}
              alt={`${track.name} album cover`}
              className="relative z-10 w-full h-full object-cover transition-all duration-300 group-hover:scale-105 group-hover:brightness-75"
            />
          </>
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-green-500/30 to-green-400/20 flex items-center justify-center">
            <Music className="w-10 h-10 text-green-400" />
          </div>
        )}

        {/* Centred play button — fades in on hover */}
        <div className="absolute inset-0 z-20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          {spotifyUrl ? (
            <a
              href={spotifyUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="w-12 h-12 bg-green-500 rounded-full flex items-center justify-center shadow-2xl hover:scale-110 transition-transform duration-150"
              title="Open in Spotify"
            >
              <PlayCircle className="w-7 h-7 text-white" />
            </a>
          ) : (
            <div className="w-12 h-12 bg-green-500/80 rounded-full flex items-center justify-center shadow-2xl">
              <PlayCircle className="w-7 h-7 text-white" />
            </div>
          )}
        </div>
      </div>

      {/* Track info */}
      <div className="px-0.5">
        <h4 className="text-sm font-semibold text-white truncate leading-snug">{track.name}</h4>
        <p className="text-xs text-gray-400 truncate mt-0.5">{track.artists.join(', ')}</p>
      </div>
    </div>
  );
};

const DashboardContent = ({
  userProfile,
  tasteProfile,
  isTasteProfileLoading,
  tasteProfileError,
  onRetryTasteProfile,
  recommendations,
  isLoading,
  onGenerateRecommendations,
  onSavePlaylist
}: {
  userProfile: UserProfile | null;
  tasteProfile: TasteProfile | null;
  isTasteProfileLoading: boolean;
  tasteProfileError: boolean;
  onRetryTasteProfile: () => void;
  recommendations: RecommendationTrack[];
  isLoading: boolean;
  onGenerateRecommendations: () => void;
  onSavePlaylist: () => void;
}) => {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Welcome Card */}
      <GlassCard className="lg:col-span-2">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">
              Your Spotify Analytics
            </h2>
            <p className="text-gray-300">AI-powered insights from your music library</p>
          </div>
          <button
            onClick={onGenerateRecommendations}
            disabled={isLoading}
            className="bg-gradient-to-r from-green-500 to-green-400 text-white px-6 py-3 rounded-xl font-medium shadow-lg hover:shadow-xl transition-all duration-200 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Generate Playlist
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-blue-500/20 to-purple-500/20 rounded-xl p-4 border border-white/10">
            <div className="flex items-center gap-3 mb-2">
              <TrendingUp className="w-5 h-5 text-blue-400" />
              <span className="text-sm text-gray-300">Tracks Analyzed</span>
            </div>
            <p className="text-2xl font-bold text-white">
              {userProfile?.total_tracks_analyzed ?? '—'}
            </p>
            <p className="text-xs text-gray-400">From your Spotify library</p>
          </div>

          <div className="bg-gradient-to-br from-green-500/20 to-emerald-500/20 rounded-xl p-4 border border-white/10">
            <div className="flex items-center gap-3 mb-2">
              <Music className="w-5 h-5 text-green-400" />
              <span className="text-sm text-gray-300">Recommendations</span>
            </div>
            <p className="text-2xl font-bold text-white">{recommendations.length}</p>
            <p className="text-xs text-gray-400">Generated for you</p>
          </div>

          <div className="bg-gradient-to-br from-pink-500/20 to-rose-500/20 rounded-xl p-4 border border-white/10">
            <div className="flex items-center gap-3 mb-2">
              <Heart className="w-5 h-5 text-pink-400" />
              <span className="text-sm text-gray-300">Similarity Score</span>
            </div>
            <p className="text-2xl font-bold text-white">
              {recommendations.length > 0
                ? `${Math.round((recommendations[0]?.similarity_score ?? 0) * 100)}%`
                : '—'
              }
            </p>
            <p className="text-xs text-gray-400">AI accuracy</p>
          </div>
        </div>
      </GlassCard>

      {/* Taste Profile */}
      <TasteProfileCard
        profile={tasteProfile}
        isLoading={isTasteProfileLoading}
        hasError={tasteProfileError}
        onRetry={onRetryTasteProfile}
      />

      {/* Recommendations */}
      <GlassCard className="lg:col-span-3">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">AI Recommendations</h3>
          {recommendations.length > 0 && (
            <button
              onClick={onSavePlaylist}
              className="bg-green-500 text-white px-4 py-2 rounded-lg hover:bg-green-600 transition-colors flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              Save Playlist
            </button>
          )}
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-8 h-8 animate-spin text-green-500" />
          </div>
        ) : recommendations.length > 0 ? (
          <div className="space-y-3 max-h-[32rem] overflow-y-auto pr-1">
            {recommendations.map((track, index) => (
              <RecommendationCard key={track.id || index} track={track} />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <Sparkles className="w-10 h-10 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400 mb-1 font-medium">No recommendations yet</p>
            <p className="text-sm text-gray-500 mb-5">Hit generate to get a personalised playlist from your library.</p>
            <button
              onClick={onGenerateRecommendations}
              className="bg-gradient-to-r from-green-500 to-green-400 text-white px-6 py-2.5 rounded-xl font-medium hover:shadow-lg hover:shadow-green-500/20 transition-all"
            >
              Generate Your First Playlist
            </button>
          </div>
        )}

        {recommendations.length > 0 && (
          <button
            onClick={onGenerateRecommendations}
            className="w-full mt-4 py-3 border border-white/20 rounded-xl text-gray-300 hover:bg-white/5 transition-all duration-200"
          >
            Generate New Recommendations
          </button>
        )}
      </GlassCard>

    </div>
  );
};

const DiscoverTab = ({ token }: { token: string }) => {
  const [explorer, setExplorer] = useState<DiscoverExplorerPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(false);
  const [genreTracks, setGenreTracks] = useState<RecommendationTrack[]>([]);
  const [selectedGenre, setSelectedGenre] = useState<string | null>(null);
  const [genreLoading, setGenreLoading] = useState(false);
  const [selectedArtist, setSelectedArtist] = useState<DiscoverArtistDetail | null>(null);
  const [artistLoading, setArtistLoading] = useState(false);

  const loadExplorer = async () => {
    setIsLoading(true);
    setError(false);
    try {
      const response = await fetch(`${API_BASE}/api/recommendations/discover/explorer`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to load explorer');
      const data = await response.json();
      setExplorer(data);
    } catch (error) {
      console.error('Error loading discover explorer:', error);
      setError(true);
    } finally {
      setIsLoading(false);
    }
  };

  const loadGenreFeed = async (genre: string) => {
    setSelectedGenre(genre);
    setGenreLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/recommendations/discover/genre/${encodeURIComponent(genre)}?limit=12`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await response.json();
      setGenreTracks(data.tracks || []);
    } catch (error) {
      console.error('Error loading genre feed:', error);
      setGenreTracks([]);
    } finally {
      setGenreLoading(false);
    }
  };

  const loadArtistDetail = async (artistId: string) => {
    setArtistLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/recommendations/discover/artist/${artistId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await response.json();
      if (response.ok) setSelectedArtist(data);
    } catch (error) {
      console.error('Error loading artist detail:', error);
      setSelectedArtist(null);
    } finally {
      setArtistLoading(false);
    }
  };

  useEffect(() => {
    if (token) loadExplorer();
  }, [token]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Music Explorer</h2>
        <p className="text-gray-300">Step outside your algorithm bubble and explore where your taste can go next.</p>
      </div>

      <GlassCard>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Outside Your Bubble</h3>
          <button
            onClick={loadExplorer}
            className="text-sm text-green-400 hover:text-green-300 transition-colors"
          >
            Refresh Explorer
          </button>
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center h-24">
            <Loader2 className="w-8 h-8 animate-spin text-green-500" />
          </div>
        ) : error || !explorer ? (
          <div className="flex flex-col items-center gap-3 py-8">
            <p className="text-sm text-gray-400">Explorer data unavailable.</p>
            <button
              onClick={loadExplorer}
              className="text-xs text-green-400 hover:text-green-300 border border-green-500/30 px-4 py-1.5 rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {explorer.outside_your_bubble.map((card) => (
                <button
                  key={card.genre}
                  onClick={() => loadGenreFeed(card.genre)}
                  className="text-left p-4 rounded-xl border border-white/15 bg-white/5 hover:bg-white/10 hover:border-green-500/50 transition-all"
                >
                  <p className="text-sm font-semibold text-white mb-1">{card.genre}</p>
                  <p className="text-xs text-gray-300 mb-2">{card.description}</p>
                  <p className="text-xs text-green-300 truncate">{card.sample_artists.join(' • ') || 'Tap to explore tracks'}</p>
                </button>
              ))}
            </div>
          </>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Artists You Should Know</h3>
        {isLoading || !explorer ? (
          <div className="h-24 flex items-center justify-center">
            <Loader2 className="w-7 h-7 animate-spin text-green-500" />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {explorer.artists_you_should_know.slice(0, 9).map((artist) => (
              <button
                key={artist.id}
                onClick={() => loadArtistDetail(artist.id)}
                className="text-left p-3 rounded-xl border border-white/15 bg-white/5 hover:bg-white/10 transition-all"
              >
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-12 h-12 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
                    {artist.image_url ? (
                      <img src={artist.image_url} alt={artist.name} className="w-full h-full object-cover" />
                    ) : (
                      <Music className="w-5 h-5 text-gray-300" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{artist.name}</p>
                    <p className="text-xs text-gray-400 truncate">{artist.genres.join(', ') || 'Genre blend'}</p>
                  </div>
                </div>
                <p className="text-xs text-green-300">{artist.reason}</p>
              </button>
            ))}
          </div>
        )}
      </GlassCard>

      {(selectedGenre || genreTracks.length > 0) && (
        <GlassCard>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">
              {selectedGenre ? `Exploring ${selectedGenre}` : 'Genre Feed'}
            </h3>
            {selectedGenre && (
              <button onClick={() => loadGenreFeed(selectedGenre)} className="text-sm text-green-400 hover:text-green-300">
                Refresh
              </button>
            )}
          </div>
          {genreLoading ? (
            <div className="h-24 flex items-center justify-center">
              <Loader2 className="w-7 h-7 animate-spin text-green-500" />
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {genreTracks.slice(0, 12).map((track, index) => (
                <AlbumTrackCard key={track.id || index} track={track} />
              ))}
            </div>
          )}
        </GlassCard>
      )}

      {selectedArtist && (
        <GlassCard>
          <div className="flex items-start justify-between mb-4 gap-3">
            <div>
              <h3 className="text-lg font-semibold text-white">{selectedArtist.artist.name}</h3>
              <p className="text-sm text-gray-300">{selectedArtist.artist.reason}</p>
            </div>
            {artistLoading && <Loader2 className="w-5 h-5 animate-spin text-green-500" />}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-300 mb-2">Top Tracks</p>
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {selectedArtist.top_tracks.slice(0, 6).map((track, index) => (
                  <RecommendationCard key={track.id || index} track={track} />
                ))}
              </div>
            </div>
            <div>
              <p className="text-sm text-gray-300 mb-2">Similar Artists</p>
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {selectedArtist.similar_artists.slice(0, 8).map((artist) => (
                  <div key={artist.id} className="p-2 rounded-lg bg-white/5 border border-white/10">
                    <p className="text-sm text-white">{artist.name}</p>
                    <p className="text-xs text-gray-400">{artist.genres.join(', ') || 'Genre blend'}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Underground Radar</h3>
          {!explorer ? (
            <div className="h-24 flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-green-500" /></div>
          ) : (
            <div className="space-y-3 max-h-[30rem] overflow-y-auto pr-1">
              {explorer.underground_radar.slice(0, 12).map((track, index) => (
                <div key={track.id || index} className="relative">
                  <RecommendationCard track={track} />
                  <span className="absolute top-2 right-2 text-[10px] bg-green-500/20 text-green-300 px-2 py-0.5 rounded-full">
                    {track.popularity}/100
                  </span>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-2">Trending Outside Your Taste</h3>
          {!explorer ? (
            <div className="h-24 flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-green-500" /></div>
          ) : (
            <>
              <p className="text-xs text-gray-400 mb-3">
                Scenes outside your usual taste
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {explorer.trending_outside_your_taste.slice(0, 9).map((track, index) => (
                  <AlbumTrackCard key={track.id || index} track={track} />
                ))}
              </div>
            </>
          )}
        </GlassCard>
      </div>
    </div>
  );
};

const AnalyticsTab = ({ token, userProfile }: { token: string; userProfile: UserProfile | null }) => {
  const [timeRange, setTimeRange] = useState('medium_term');
  const [topTracks, setTopTracks] = useState<TopTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [insights, setInsights] = useState<ListeningInsightsPayload | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState(false);

  const timeRanges = [
    { id: 'short_term', label: 'Last 4 Weeks' },
    { id: 'medium_term', label: 'Last 6 Months' },
    { id: 'long_term', label: 'All Time' },
  ];

  useEffect(() => {
    if (token) {
      loadTopTracks();
      loadInsights();
    }
  }, [token, timeRange]);

  const loadTopTracks = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/recommendations/top-tracks?time_range=${timeRange}&limit=20`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await response.json();
      setTopTracks(data.top_tracks || []);
    } catch (error) {
      console.error('Error loading top tracks:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadInsights = async () => {
    setInsightsLoading(true);
    setInsightsError(false);
    try {
      const data = await fetchListeningInsights(token, timeRange as 'short_term' | 'medium_term' | 'long_term');
      if (!data) {
        setInsightsError(true);
        setInsights(null);
      } else {
        setInsights(data);
      }
    } catch {
      setInsightsError(true);
      setInsights(null);
    } finally {
      setInsightsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Music Analytics</h2>
        <p className="text-gray-300">Deep insights into your musical preferences and listening patterns</p>
      </div>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Time Period</h3>
        <div className="flex gap-3">
          {timeRanges.map((range) => (
            <button
              key={range.id}
              onClick={() => setTimeRange(range.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-200 ${
                timeRange === range.id
                  ? 'bg-green-500 text-white'
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
            >
              <Clock className="w-4 h-4" />
              <span className="text-sm font-medium">{range.label}</span>
            </button>
          ))}
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Listening Insights</h3>
          {insightsLoading ? (
            <div className="flex items-center justify-center h-40">
              <Loader2 className="w-8 h-8 animate-spin text-green-500" />
            </div>
          ) : insightsError || !insights ? (
            <div className="text-center py-10">
              <p className="text-sm text-gray-400 mb-3">Listening insights unavailable</p>
              <button
                onClick={loadInsights}
                className="text-xs text-green-400 hover:text-green-300 border border-green-500/30 px-3 py-1 rounded-lg transition-colors"
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-green-300">{insights.archetype}</p>
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-xs text-gray-400">Discovery Score</p>
                <p className="text-xl font-bold text-white">{Math.round(insights.listening_insights.discovery_score * 100)}%</p>
              </div>
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-xs text-gray-400">Artist Loyalty</p>
                <p className="text-xl font-bold text-white">{Math.round(insights.listening_insights.artist_loyalty * 100)}%</p>
              </div>
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-xs text-gray-400">Mainstream Index</p>
                <p className="text-xl font-bold text-white">{Math.round(insights.listening_insights.mainstream_index * 100)}%</p>
              </div>
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Your Sound Profile</h3>
          {insightsLoading ? (
            <div className="flex items-center justify-center h-40">
              <Loader2 className="w-8 h-8 animate-spin text-green-500" />
            </div>
          ) : insightsError || !insights?.sound_profile?.genre_breakdown?.length ? (
            <div className="text-center py-10">
              <p className="text-sm text-gray-400">No genre breakdown available</p>
            </div>
          ) : (
            <div className="space-y-3">
              {insights.sound_profile.genre_breakdown.map((g) => (
                <div key={g.genre}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-gray-300">{g.genre}</span>
                    <span className="text-gray-400">{g.percentage}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-white/10">
                    <div
                      className="h-2 rounded-full bg-gradient-to-r from-purple-500 to-green-400"
                      style={{ width: `${Math.max(2, Math.min(100, g.percentage))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Hidden Gems</h3>
        {insightsLoading ? (
          <div className="flex items-center justify-center h-24">
            <Loader2 className="w-6 h-6 animate-spin text-green-500" />
          </div>
        ) : insightsError || !insights?.hidden_gems?.length ? (
          <p className="text-sm text-gray-400">No hidden gems found right now.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {insights.hidden_gems.slice(0, 5).map((track) => (
              <div key={track.id} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg">
                <div className="w-12 h-12 rounded-lg overflow-hidden bg-white/10 flex-shrink-0">
                  {track.album_image_url ? (
                    <img src={track.album_image_url} alt={`${track.name} cover`} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Music className="w-5 h-5 text-gray-400" />
                    </div>
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-white font-medium truncate">{track.name}</p>
                  <p className="text-xs text-gray-400 truncate">{track.artists.join(', ')}</p>
                  <p className="text-xs text-green-400">Popularity {track.popularity}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">
          Your Top Tracks ({timeRanges.find(r => r.id === timeRange)?.label})
        </h3>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-8 h-8 animate-spin text-green-500" />
          </div>
        ) : topTracks.length > 0 ? (
          <div className="space-y-3">
            {topTracks.slice(0, 10).map((track, index) => (
              <div key={track.id} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg">
                <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-green-600 rounded-lg flex items-center justify-center">
                  <span className="text-white font-bold text-sm">#{index + 1}</span>
                </div>
                <div className="w-12 h-12 rounded-lg overflow-hidden bg-white/10 flex-shrink-0">
                  {getTopTrackAlbumImage(track) ? (
                    <img
                      src={getTopTrackAlbumImage(track)!}
                      alt={`${track.name} album cover`}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Music className="w-5 h-5 text-gray-400" />
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-white truncate">{track.name}</h4>
                  <p className="text-sm text-gray-400 truncate">
                    {track.artists?.map(a => a.name).join(', ')}
                  </p>
                  {track.popularity && (
                    <div className="flex items-center gap-1 mt-1">
                      <Star className="w-3 h-3 text-yellow-500 fill-current" />
                      <span className="text-xs text-gray-400">{track.popularity}% popularity</span>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:bg-pink-500/20 transition-colors">
                    <Heart className="w-4 h-4 text-gray-300" />
                  </button>
                  {track.preview_url && (
                    <button className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center hover:bg-green-500/30 transition-colors">
                      <PlayCircle className="w-4 h-4 text-green-500" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <BarChart3 className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-400">No top tracks data available for this period</p>
          </div>
        )}
      </GlassCard>
    </div>
  );
};

const PlaylistsTab = ({ token }: { token: string }) => {
  const [prompt, setPrompt] = useState('');
  const [playlistTitle, setPlaylistTitle] = useState('');
  const [tracks, setTracks] = useState<Array<{
    track_id: string;
    name: string;
    artist: string;
    artists?: string[];
    album?: string;
    album_cover_url?: string | null;
    album_images?: Array<{ url: string; width?: number; height?: number }>;
    spotify_url: string;
  }>>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');
  const [exportedUrl, setExportedUrl] = useState('');

  const quickPrompts = [
    { label: 'Chill', prompt: 'Chill evening unwind' },
    { label: 'Workout', prompt: 'Gym trap workout energy' },
    { label: 'Party', prompt: 'Party dance bangers' },
    { label: 'Focus', prompt: 'Focus deep work flow' },
    { label: 'Late Night', prompt: 'Late night drive' },
  ];

  const handleGenerate = async (promptOverride?: string) => {
    const activePrompt = (promptOverride || prompt).trim();
    if (!activePrompt) {
      setError('Enter a vibe or prompt to generate a playlist.');
      return;
    }

    setIsGenerating(true);
    setError('');
    setExportedUrl('');

    try {
      const response = await fetch(`${API_BASE}/api/playlists/generate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ prompt: activePrompt, limit: 30 }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Playlist generation failed');
      }

      setPrompt(activePrompt);
      setPlaylistTitle(data.playlist_title || `${activePrompt} — curated by BlessedEar`);
      setTracks(coerceGeneratedTracks(data.tracks));
    } catch (err: any) {
      setError(err?.message || 'Playlist generation failed');
      setTracks([]);
      setPlaylistTitle('');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExport = async () => {
    if (!tracks.length || !prompt.trim()) return;
    setIsExporting(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE}/api/playlists/export`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt,
          tracks,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Spotify export failed');
      }
      setExportedUrl(data.spotify_url || '');
    } catch (err: any) {
      setError(err?.message || 'Spotify export failed');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">AI Playlist Generator</h2>
        <p className="text-gray-300">Generate AI playlists instantly based on your vibe.</p>
      </div>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Playlist Generator</h3>
        <div className="flex flex-col md:flex-row gap-3">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe your vibe (e.g. late night drive, sad indie, gym trap)..."
            className="flex-1 bg-white/5 border border-white/20 text-white placeholder:text-gray-500 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-green-500/40"
          />
          <button
            onClick={() => handleGenerate()}
            disabled={isGenerating}
            className="bg-gradient-to-r from-green-500 to-green-400 text-white px-6 py-3 rounded-xl font-medium hover:scale-[1.02] transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            Generate Playlist
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {quickPrompts.map((item) => (
            <button
              key={item.label}
              onClick={() => handleGenerate(item.prompt)}
              className="text-sm px-3 py-1.5 rounded-full border border-white/20 text-gray-200 hover:bg-white/10 transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>
      </GlassCard>

      <GlassCard>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-white">Generated Playlist Preview</h3>
            {playlistTitle ? <p className="text-sm text-gray-400 mt-1">{playlistTitle}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {tracks.length > 0 && (
              <button
                onClick={() => handleGenerate()}
                disabled={isGenerating}
                className="px-3 py-2 rounded-lg border border-white/20 text-gray-200 hover:bg-white/10 transition-colors disabled:opacity-60"
              >
                Regenerate Playlist
              </button>
            )}
            <button
              onClick={handleExport}
              disabled={!tracks.length || isExporting}
              className="px-4 py-2 rounded-lg bg-green-500 text-white hover:bg-green-600 transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isExporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
              Save to Spotify
            </button>
          </div>
        </div>

        {error ? <p className="text-sm text-rose-300 mb-3">{error}</p> : null}
        {exportedUrl ? (
          <a
            href={exportedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-green-300 hover:text-green-200 mb-3 inline-flex items-center gap-1"
          >
            Playlist exported successfully — open in Spotify
            <ExternalLink className="w-3 h-3" />
          </a>
        ) : null}

        {tracks.length === 0 ? (
          <div className="text-center py-10 text-gray-400">
            Enter a prompt or tap a quick mood to generate a 20–40 track playlist.
          </div>
        ) : (
          <div className="max-h-[30rem] overflow-y-auto space-y-2 pr-1">
            {tracks.map((track, index) => (
              <div key={`${track.track_id}-${index}`} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg">
                <div className="w-12 h-12 rounded-lg overflow-hidden bg-white/10 flex-shrink-0">
                  {track.album_cover_url ? (
                    <img src={track.album_cover_url} alt={`${track.name} cover`} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Music className="w-5 h-5 text-gray-400" />
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{track.name}</p>
                  <p className="text-xs text-gray-400 truncate">{track.artist}</p>
                </div>
                <a
                  href={track.spotify_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:bg-green-500/20 transition-colors"
                >
                  <ExternalLink className="w-4 h-4 text-gray-300" />
                </a>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
};

export default function DashboardLayout() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [recommendations, setRecommendations] = useState<RecommendationTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [playlistName, setPlaylistName] = useState('');
  const [playlistDescription, setPlaylistDescription] = useState('');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [saveError, setSaveError] = useState('');
  const [currentMood, setCurrentMood] = useState<string | null>(null);
  const [tasteProfile, setTasteProfile] = useState<TasteProfile | null>(null);
  const [tasteProfileLoading, setTasteProfileLoading] = useState(false);
  const [tasteProfileError, setTasteProfileError] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authCode = params.get('code');
    const isFresh = params.get('fresh');

    if (authCode) {
      sessionStorage.removeItem('access_token');

      window.history.replaceState({}, '', '/dashboard');

      fetch(`${API_BASE}/api/auth/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: authCode }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.access_token) {
            setUserProfile(null);
            setCurrentUser(null);
            setRecommendations([]);
            setTasteProfile(null);
            setTasteProfileError(false);
            setTasteProfileLoading(false);

            sessionStorage.setItem('access_token', data.access_token);
            setToken(data.access_token);
          } else {
            window.location.href = '/login';
          }
        })
        .catch(() => {
          window.location.href = '/login';
        });
    } else {
      const stored = sessionStorage.getItem('access_token');
      if (stored) {
        setToken(stored);
      }
    }
  }, []);

  useEffect(() => {
    if (token) {
      loadUserData();
    }
  }, [token]);

  const loadUserData = async () => {
    if (!token) return;

    setIsLoading(true);
    setTasteProfileLoading(true);
    setTasteProfileError(false);
    setTasteProfile(null);
    try {
      const [profile, user] = await Promise.all([
        getUserProfile(token),
        getCurrentUser(token),
      ]);

      setUserProfile(profile);
      setCurrentUser(user);

      if (profile) {
        const recs = await generateRecommendations(token, { limit: 20 });
        setRecommendations(recs);
      }

      window.setTimeout(() => {
        void loadTasteProfile(token);
      }, 400);
    } catch (error) {
      console.error('Error loading user data:', error);
      setTasteProfileLoading(false);
      setTasteProfileError(true);
    } finally {
      setIsLoading(false);
    }
  };

  const loadTasteProfile = async (tokenOverride?: string) => {
    const activeToken = tokenOverride || token;
    if (!activeToken) return;

    setTasteProfileLoading(true);
    setTasteProfileError(false);
    setTasteProfile(null);

    const result = await fetchTasteProfile(activeToken);
    if (result) {
      setTasteProfile(result);
      if (process.env.NODE_ENV !== 'production') {
        console.debug('[TasteProfile] payload', result);
      }
    } else {
      setTasteProfileError(true);
    }
    setTasteProfileLoading(false);
  };

  const handleGenerateRecommendations = async () => {
    if (!token) return;

    setIsLoading(true);
    setCurrentMood(null);
    try {
      const recs = await generateRecommendations(token, { limit: 20 });
      setRecommendations(recs);
    } catch (error) {
      console.error('Error generating recommendations:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSavePlaylist = async () => {
    if (!token || recommendations.length === 0) return;

    setSaveStatus('saving');
    setSaveError('');
    try {
      const response = await fetch(`${API_BASE}/api/playlists/save`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: playlistName,
          description: playlistDescription,
          tracks: recommendations,
          mood: currentMood,
          generation_type: currentMood ? 'mood' : 'recommendation',
        }),
      });

      if (response.ok) {
        setSaveStatus('success');
        setTimeout(() => {
          setShowSaveModal(false);
          setPlaylistName('');
          setPlaylistDescription('');
          setSaveStatus('idle');
          setSaveError('');
        }, 1200);
      } else {
        const err = await response.json();
        setSaveStatus('error');
        setSaveError(err.detail || 'Failed to save playlist');
      }
    } catch {
      setSaveStatus('error');
      setSaveError('Could not connect to server. Please try again.');
    }
  };

  const openSaveModal = () => {
    const defaultName = currentMood
      ? `${currentMood.charAt(0).toUpperCase() + currentMood.slice(1)} Vibes`
      : `AI Recommendations ${new Date().toLocaleDateString()}`;
    setPlaylistName(defaultName);
    setPlaylistDescription('');
    setSaveStatus('idle');
    setSaveError('');
    setShowSaveModal(true);
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 flex flex-col items-center justify-center gap-4">
        <div className="w-12 h-12 bg-gradient-to-br from-green-500 to-green-600 rounded-2xl flex items-center justify-center mb-2">
          <Music className="w-7 h-7 text-white" />
        </div>
        <Loader2 className="w-6 h-6 animate-spin text-green-500" />
        <p className="text-sm text-gray-500">Loading your music profile…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 opacity-30">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
      </div>

      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        userDisplayName={currentUser?.display_name}
      />

      <main className="ml-64 p-8">
        <div>
          {activeTab === 'dashboard' && (
            <DashboardContent
              userProfile={userProfile}
              tasteProfile={tasteProfile}
              isTasteProfileLoading={tasteProfileLoading}
              tasteProfileError={tasteProfileError}
              onRetryTasteProfile={() => token && loadTasteProfile(token)}
              recommendations={recommendations}
              isLoading={isLoading}
              onGenerateRecommendations={handleGenerateRecommendations}
              onSavePlaylist={openSaveModal}
            />
          )}
          {activeTab === 'discover' && <DiscoverTab token={token} />}
          {activeTab === 'analytics' && <AnalyticsTab token={token} userProfile={userProfile} />}
          {activeTab === 'playlists' && <PlaylistsTab token={token} />}
        </div>
      </main>

      {/* Save Playlist Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="backdrop-blur-xl bg-black/80 border border-white/20 p-6 rounded-2xl max-w-md w-full mx-4 shadow-2xl">
            <h3 className="text-lg font-semibold text-white mb-4">Save Playlist</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-2">Playlist Name</label>
                <input
                  type="text"
                  value={playlistName}
                  onChange={(e) => setPlaylistName(e.target.value)}
                  className="w-full bg-white/5 text-white rounded-xl px-4 py-2.5 border border-white/20 focus:border-green-500/60 focus:outline-none focus:ring-1 focus:ring-green-500/30 placeholder:text-gray-500"
                  placeholder="Enter playlist name"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-2">Description <span className="text-gray-500">(optional)</span></label>
                <textarea
                  value={playlistDescription}
                  onChange={(e) => setPlaylistDescription(e.target.value)}
                  className="w-full bg-white/5 text-white rounded-xl px-4 py-2.5 border border-white/20 focus:border-green-500/60 focus:outline-none focus:ring-1 focus:ring-green-500/30 placeholder:text-gray-500 resize-none"
                  placeholder="What's the vibe?"
                  rows={3}
                />
              </div>

              <p className="text-xs text-gray-500">
                {recommendations.length} tracks · {currentMood ? `${currentMood} mood` : 'AI recommendations'}
              </p>

              {saveStatus === 'error' && (
                <p className="text-sm text-rose-300">{saveError}</p>
              )}
              {saveStatus === 'success' && (
                <p className="text-sm text-green-400">Playlist saved!</p>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowSaveModal(false);
                  setPlaylistName('');
                  setPlaylistDescription('');
                  setSaveStatus('idle');
                  setSaveError('');
                }}
                className="flex-1 bg-white/10 hover:bg-white/20 text-white py-2.5 rounded-xl border border-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSavePlaylist}
                disabled={!playlistName.trim() || saveStatus === 'saving' || saveStatus === 'success'}
                className="flex-1 bg-green-500 text-white py-2.5 rounded-xl hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {saveStatus === 'saving' && <Loader2 className="w-4 h-4 animate-spin" />}
                {saveStatus === 'success' ? 'Saved!' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
