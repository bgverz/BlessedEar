'use client'

import React, { useState, useEffect } from 'react';
import { Music, BarChart3, Sparkles, User, PlayCircle, Heart, TrendingUp, Loader2, Clock, Star, ExternalLink } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

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
  preview_url?: string;
  album?: string;
  album_images?: Array<{url: string; width: number; height: number}>;
  external_urls?: {spotify?: string};
}

interface TopTrack {
  id: string;
  name: string;
  artists: { name: string }[];
  album: { name: string };
  popularity: number;
  preview_url?: string;
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
    body: JSON.stringify({ limit: 10, ...options }),
  });
  const data = await response.json();
  return data.tracks || [];
}

async function generateMoodPlaylist(token: string, mood: string) {
  const response = await fetch(`${API_BASE}/api/recommendations/mood-playlist`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ mood, limit: 8 }),
  });
  const data = await response.json();
  return data.tracks || [];
}

const GlassCard = ({ children, className = "", ...props }) => (
  <div
    className={`backdrop-blur-md bg-white/10 border border-white/20 rounded-2xl p-6 shadow-lg ${className}`}
    {...props}
  >
    {children}
  </div>
);

const Sidebar = ({ activeTab, setActiveTab, userDisplayName }) => {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { id: 'discover', label: 'Discover', icon: Sparkles },
    { id: 'playlists', label: 'Playlists', icon: Music },
    { id: 'analytics', label: 'Analytics', icon: TrendingUp },
    { id: 'profile', label: 'Profile', icon: User },
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
            onClick={() => window.location.href = '/login'}
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

const AudioFeatureRadar = ({ userProfile }: { userProfile: UserProfile | null }) => {
  if (!userProfile) {
    return (
      <GlassCard className="h-80">
        <h3 className="text-lg font-semibold text-white mb-4">Your Music DNA</h3>
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-8 h-8 animate-spin text-green-500" />
        </div>
      </GlassCard>
    );
  }

  const features = [
    { name: 'Energy', value: userProfile?.avg_features?.energy || 0, color: '#FF6B6B' },
    { name: 'Valence', value: userProfile?.avg_features?.valence || 0, color: '#4ECDC4' },
    { name: 'Dance', value: userProfile?.avg_features?.danceability || 0, color: '#45B7D1' },
    { name: 'Acoustic', value: userProfile?.avg_features?.acousticness || 0, color: '#96CEB4' },
    { name: 'Speech', value: userProfile?.avg_features?.speechiness || 0, color: '#FFEAA7' },
    { name: 'Liveness', value: userProfile?.avg_features?.liveness || 0, color: '#DDA0DD' },
  ];

  return (
    <GlassCard className="h-80">
      <h3 className="text-lg font-semibold text-white mb-4">Your Music DNA</h3>
      <div className="relative w-full h-48 flex items-center justify-center">
        <div className="relative w-40 h-40">
          {features.map((feature, index) => {
            const angle = (index * 60) - 90;
            const x = Math.cos(angle * Math.PI / 180) * (60 + feature.value * 20);
            const y = Math.sin(angle * Math.PI / 180) * (60 + feature.value * 20);
            
            return (
              <div
                key={feature.name}
                className="absolute w-3 h-3 rounded-full"
                style={{ 
                  backgroundColor: feature.color,
                  left: `calc(50% + ${x}px - 6px)`,
                  top: `calc(50% + ${y}px - 6px)`,
                  boxShadow: `0 0 20px ${feature.color}40`
                }}
              />
            );
          })}
          <div className="absolute inset-0 rounded-full border border-white/20"></div>
          <div className="absolute inset-4 rounded-full border border-white/10"></div>
          <div className="absolute inset-8 rounded-full border border-white/5"></div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mt-4">
        {features.map((feature) => (
          <div key={feature.name} className="flex items-center gap-1">
            <div 
              className="w-2 h-2 rounded-full" 
              style={{ backgroundColor: feature.color }}
            />
            <span className="text-xs text-gray-300">{feature.name}</span>
          </div>
        ))}
      </div>
    </GlassCard>
  );
};

const RecommendationCard = ({ track }: { track: RecommendationTrack }) => (
  <div className="backdrop-blur-sm bg-white/5 border border-white/10 rounded-xl p-4 hover:bg-white/10 transition-all duration-200 cursor-pointer group">
    <div className="flex items-center gap-3">
      <div className="w-12 h-12 bg-gradient-to-br from-green-500/20 to-green-400/20 rounded-lg flex items-center justify-center group-hover:from-green-500/30 group-hover:to-green-400/30 transition-all duration-200">
        <Music className="w-6 h-6 text-green-500" />
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="font-medium text-white truncate">{track.name}</h4>
        <p className="text-sm text-gray-400 truncate">{track.artists.join(', ')}</p>
        <p className="text-xs text-green-400">{track.recommendation_reason}</p>
      </div>
      <div className="flex items-center gap-2">
        <button className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:bg-green-500/20 transition-colors">
          <Heart className="w-4 h-4 text-gray-300" />
        </button>
        {track.preview_url && (
          <button className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center hover:bg-green-500/30 transition-colors">
            <PlayCircle className="w-4 h-4 text-green-500" />
          </button>
        )}
      </div>
    </div>
  </div>
);

const DashboardContent = ({ 
  userProfile, 
  recommendations, 
  isLoading, 
  onGenerateRecommendations,
  onGenerateMoodPlaylist 
}: {
  userProfile: UserProfile | null;
  recommendations: RecommendationTrack[];
  isLoading: boolean;
  onGenerateRecommendations: () => void;
  onGenerateMoodPlaylist: (mood: string) => void;
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
              {userProfile?.total_tracks_analyzed || 0}
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
                ? Math.round(recommendations[0]?.similarity_score * 100) || 'N/A'
                : 'N/A'
              }%
            </p>
            <p className="text-xs text-gray-400">AI accuracy</p>
          </div>
        </div>
      </GlassCard>

      {/* Audio Features */}
      <AudioFeatureRadar userProfile={userProfile} />

      {/* Recommendations */}
      <GlassCard className="lg:col-span-2">
        <h3 className="text-lg font-semibold text-white mb-4">AI Recommendations</h3>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-8 h-8 animate-spin text-green-500" />
          </div>
        ) : recommendations.length > 0 ? (
          <div className="space-y-3">
            {recommendations.map((track, index) => (
              <RecommendationCard key={track.id || index} track={track} />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-gray-400 mb-4">No recommendations yet</p>
            <button 
              onClick={onGenerateRecommendations}
              className="bg-green-500 text-white px-6 py-2 rounded-lg hover:bg-green-600 transition-colors"
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

      {/* Quick Actions */}
      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Quick Actions</h3>
        <div className="space-y-3">
          <button 
            onClick={() => onGenerateMoodPlaylist('happy')}
            className="w-full bg-gradient-to-r from-purple-500/20 to-pink-500/20 border border-purple-500/30 text-white py-3 rounded-xl hover:from-purple-500/30 hover:to-pink-500/30 transition-all duration-200"
          >
            Happy Playlist
          </button>
          <button 
            onClick={() => onGenerateMoodPlaylist('chill')}
            className="w-full bg-gradient-to-r from-green-500/20 to-blue-500/20 border border-green-500/30 text-white py-3 rounded-xl hover:from-green-500/30 hover:to-blue-500/30 transition-all duration-200"
          >
            Chill Vibes
          </button>
          <button 
            onClick={() => onGenerateMoodPlaylist('energetic')}
            className="w-full bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/30 text-white py-3 rounded-xl hover:from-orange-500/30 hover:to-red-500/30 transition-all duration-200"
          >
            High Energy
          </button>
        </div>
      </GlassCard>
    </div>
  );
};

// NEW DISCOVER TAB COMPONENT
const DiscoverTab = ({ token }: { token: string }) => {
  const [discoverType, setDiscoverType] = useState('similar');
  const [isLoading, setIsLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationTrack[]>([]);

  const discoverOptions = [
    { id: 'similar', label: 'Similar to My Taste', description: 'Based on your listening history' },
    { id: 'new-genres', label: 'New Genres', description: 'Explore different musical styles' },
    { id: 'trending', label: 'Trending Now', description: 'Popular tracks worldwide' },
    { id: 'deep-cuts', label: 'Deep Cuts', description: 'Hidden gems and B-sides' },
  ];

  const moodOptions = [
    { id: 'happy', label: 'Happy', color: 'from-yellow-500 to-orange-500' },
    { id: 'energetic', label: 'Energetic', color: 'from-red-500 to-pink-500' },
    { id: 'chill', label: 'Chill', color: 'from-blue-500 to-cyan-500' },
    { id: 'focus', label: 'Focus', color: 'from-purple-500 to-indigo-500' },
    { id: 'sad', label: 'Melancholy', color: 'from-gray-500 to-blue-500' },
    { id: 'party', label: 'Party', color: 'from-green-500 to-emerald-500' },
  ];

  const handleDiscoverMusic = async (type: string) => {
    setIsLoading(true);
    try {
      let response;
      if (['similar', 'new-genres', 'trending', 'deep-cuts'].includes(type)) {
        response = await fetch(`${API_BASE}/api/recommendations/discover/${type}?limit=12`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        const data = await response.json();
        setRecommendations(data.tracks || []);
      } else {
        // Mood-based
        response = await fetch(`${API_BASE}/api/recommendations/mood-playlist`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ mood: type, limit: 12 }),
        });
        const data = await response.json();
        setRecommendations(data.tracks || []);
      }
    } catch (error) {
      console.error('Error discovering music:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Discover New Music</h2>
        <p className="text-gray-300">AI-powered music discovery tailored to your taste</p>
      </div>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Discovery Mode</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {discoverOptions.map((option) => (
            <button
              key={option.id}
              onClick={() => {
                setDiscoverType(option.id);
                handleDiscoverMusic(option.id);
              }}
              className={`p-4 rounded-xl border-2 transition-all duration-200 text-left ${
                discoverType === option.id
                  ? 'border-green-500 bg-green-500/10'
                  : 'border-white/20 hover:border-white/40 hover:bg-white/5'
              }`}
            >
              <h4 className="font-medium text-white text-sm">{option.label}</h4>
              <p className="text-xs text-gray-400 mt-1">{option.description}</p>
            </button>
          ))}
        </div>
      </GlassCard>

      <GlassCard>
        <h3 className="text-lg font-semibold text-white mb-4">Mood-Based Discovery</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {moodOptions.map((mood) => (
            <button
              key={mood.id}
              onClick={() => handleDiscoverMusic(mood.id)}
              className={`p-4 rounded-xl bg-gradient-to-br ${mood.color} hover:scale-105 transition-all duration-200 text-white font-medium text-sm`}
            >
              {mood.label}
            </button>
          ))}
        </div>
      </GlassCard>

      <GlassCard>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Discovered Tracks</h3>
          {recommendations.length > 0 && (
            <button 
              onClick={() => handleDiscoverMusic(discoverType)}
              className="text-sm text-green-400 hover:text-green-300 transition-colors"
            >
              Refresh
            </button>
          )}
        </div>
        
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-8 h-8 animate-spin text-green-500" />
          </div>
        ) : recommendations.length > 0 ? (
          <div className="space-y-3">
            {recommendations.map((track, index) => (
              <RecommendationCard key={track.id || index} track={track} />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <Sparkles className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-400 mb-4">Choose a discovery mode to find new music</p>
            <button 
              onClick={() => handleDiscoverMusic('similar')}
              className="bg-green-500 text-white px-6 py-2 rounded-lg hover:bg-green-600 transition-colors"
            >
              Start Discovering
            </button>
          </div>
        )}
      </GlassCard>
    </div>
  );
};

// NEW ANALYTICS TAB COMPONENT
const AnalyticsTab = ({ token, userProfile }: { token: string; userProfile: UserProfile | null }) => {
  const [timeRange, setTimeRange] = useState('medium_term');
  const [topTracks, setTopTracks] = useState<TopTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const timeRanges = [
    { id: 'short_term', label: 'Last 4 Weeks' },
    { id: 'medium_term', label: 'Last 6 Months' },
    { id: 'long_term', label: 'All Time' },
  ];

  useEffect(() => {
    if (token) {
      loadTopTracks();
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

  const AudioFeatureChart = ({ feature, value, color }: { feature: string; value: number; color: string }) => (
    <div className="bg-white/5 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-white capitalize">{feature}</span>
        <span className="text-sm text-gray-400">{Math.round(value * 100)}%</span>
      </div>
      <div className="w-full bg-gray-700 rounded-full h-2">
        <div 
          className="h-2 rounded-full transition-all duration-500"
          style={{ 
            width: `${value * 100}%`,
            backgroundColor: color,
            boxShadow: `0 0 10px ${color}40`
          }}
        />
      </div>
    </div>
  );

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
          <h3 className="text-lg font-semibold text-white mb-4">Your Music DNA</h3>
          {userProfile ? (
            <div className="space-y-3">
              <AudioFeatureChart feature="energy" value={userProfile.avg_features.energy} color="#ff6b6b" />
              <AudioFeatureChart feature="danceability" value={userProfile.avg_features.danceability} color="#4ecdc4" />
              <AudioFeatureChart feature="valence" value={userProfile.avg_features.valence} color="#45b7d1" />
              <AudioFeatureChart feature="acousticness" value={userProfile.avg_features.acousticness} color="#96ceb4" />
              <AudioFeatureChart feature="speechiness" value={userProfile.avg_features.speechiness} color="#ffeaa7" />
              <AudioFeatureChart feature="liveness" value={userProfile.avg_features.liveness} color="#dda0dd" />
            </div>
          ) : (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="w-8 h-8 animate-spin text-green-500" />
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-4">Listening Statistics</h3>
          <div className="space-y-4">
            <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <Music className="w-6 h-6 text-purple-400" />
                <div>
                  <p className="text-sm text-gray-300">Tracks Analyzed</p>
                  <p className="text-2xl font-bold text-white">{userProfile?.total_tracks_analyzed || 0}</p>
                </div>
              </div>
            </div>
            
            <div className="bg-gradient-to-r from-green-500/20 to-emerald-500/20 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <TrendingUp className="w-6 h-6 text-green-400" />
                <div>
                  <p className="text-sm text-gray-300">Top Tracks ({timeRanges.find(r => r.id === timeRange)?.label})</p>
                  <p className="text-2xl font-bold text-white">{topTracks.length}</p>
                </div>
              </div>
            </div>

            <div className="bg-gradient-to-r from-blue-500/20 to-cyan-500/20 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <BarChart3 className="w-6 h-6 text-blue-400" />
                <div>
                  <p className="text-sm text-gray-300">Average Tempo</p>
                  <p className="text-2xl font-bold text-white">{Math.round(userProfile?.avg_features.tempo || 120)} BPM</p>
                </div>
              </div>
            </div>
          </div>
        </GlassCard>
      </div>

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

export default function DashboardLayout() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [recommendations, setRecommendations] = useState<RecommendationTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    const isFresh = params.get('fresh');
    
    console.log('Token check:', urlToken ? 'Found' : 'Not found');
    console.log('Fresh login:', isFresh ? 'Yes' : 'No');
    
    if (urlToken) {
      setToken(urlToken);
      
      if (isFresh) {
        console.log('Fresh login detected - clearing all cached data');
        setUserProfile(null);
        setCurrentUser(null);
        setRecommendations([]);
        localStorage.clear();
        sessionStorage.clear();
      }
      
      window.history.replaceState({}, '', '/dashboard');
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
    try {
      const [profile, user] = await Promise.all([
        getUserProfile(token),
        getCurrentUser(token)
      ]);
      
      setUserProfile(profile);
      setCurrentUser(user);

      if (profile) {
        const recs = await generateRecommendations(token, { limit: 8 });
        setRecommendations(recs);
      }
    } catch (error) {
      console.error('Error loading user data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleGenerateRecommendations = async () => {
    if (!token) return;
    
    setIsLoading(true);
    try {
      const recs = await generateRecommendations(token, { limit: 8 });
      setRecommendations(recs);
    } catch (error) {
      console.error('Error generating recommendations:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleGenerateMoodPlaylist = async (mood: string) => {
    if (!token) return;
    
    setIsLoading(true);
    try {
      const recs = await generateMoodPlaylist(token, mood);
      setRecommendations(recs);
    } catch (error) {
      console.error('Error generating mood playlist:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      setToken(null);
      setUserProfile(null);
      setCurrentUser(null);
      setRecommendations([]);
      
      localStorage.clear();
      sessionStorage.clear();
      
      if (token) {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        });
      }
      
      window.location.href = '/login?force=true';
    } catch (error) {
      console.error('Error logging out:', error);
      window.location.href = '/login?force=true';
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-green-500" />
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
              recommendations={recommendations}
              isLoading={isLoading}
              onGenerateRecommendations={handleGenerateRecommendations}
              onGenerateMoodPlaylist={handleGenerateMoodPlaylist}
            />
          )}
          {activeTab === 'discover' && <DiscoverTab token={token} />}
          {activeTab === 'analytics' && <AnalyticsTab token={token} userProfile={userProfile} />}
          {activeTab === 'playlists' && (
            <GlassCard>
              <h2 className="text-2xl font-bold text-white mb-4">Your Playlists</h2>
              <p className="text-gray-300">Playlist management coming soon...</p>
            </GlassCard>
          )}
          {activeTab === 'profile' && (
            <GlassCard>
              <h2 className="text-2xl font-bold text-white mb-4">Profile Settings</h2>
              <p className="text-gray-300">User profile management coming soon...</p>
            </GlassCard>
          )}
        </div>
      </main>
    </div>
  );
}