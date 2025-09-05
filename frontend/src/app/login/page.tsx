'use client'

import { useState } from 'react';
import Link from 'next/link';
import { Music, Sparkles, ArrowRight, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const [isLoading, setIsLoading] = useState(false);

  const handleSpotifyLogin = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/auth/login');
      const data = await response.json();
      
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch (error) {
      console.error('Login error:', error);
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 relative overflow-hidden">
      {/* Background elements */}
      <div className="absolute inset-0 opacity-30">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
      </div>

      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6">
        <div className="text-center max-w-md">
          {/* Logo */}
          <div className="flex items-center justify-center gap-3 mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-green-400 to-green-600 rounded-2xl flex items-center justify-center">
              <Music className="w-9 h-9 text-white" />
            </div>
            <h1 className="text-5xl font-bold text-white">BlessedEar</h1>
          </div>

          {/* Hero text */}
          <h2 className="text-3xl font-bold text-white mb-4">
            Connect Your Music
          </h2>
          <p className="text-lg text-gray-300 mb-8">
            Link your Spotify account to unlock personalized AI recommendations based on your unique music taste.
          </p>

          {/* Features */}
          <div className="backdrop-blur-md bg-white/10 border border-white/20 rounded-2xl p-6 mb-8">
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-left">
                <Sparkles className="w-5 h-5 text-green-400 flex-shrink-0" />
                <span className="text-white">Analyze your music DNA</span>
              </div>
              <div className="flex items-center gap-3 text-left">
                <Music className="w-5 h-5 text-blue-400 flex-shrink-0" />
                <span className="text-white">Generate smart playlists</span>
              </div>
              <div className="flex items-center gap-3 text-left">
                <ArrowRight className="w-5 h-5 text-purple-400 flex-shrink-0" />
                <span className="text-white">Export to your Spotify</span>
              </div>
            </div>
          </div>

          {/* Login Button */}
          <button
            onClick={handleSpotifyLogin}
            disabled={isLoading}
            className="w-full bg-gradient-to-r from-green-500 to-green-600 text-white py-4 px-8 rounded-xl font-semibold text-lg hover:from-green-600 hover:to-green-700 transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Connecting...
              </>
            ) : (
              <>
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.42 1.56-.299.421-1.02.599-1.559.3z"/>
                </svg>
                Connect with Spotify
              </>
            )}
          </button>

          {/* Back to home */}
          <div className="mt-6">
            <Link href="/" className="text-gray-400 hover:text-white transition-colors">
              ← Back to home
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}