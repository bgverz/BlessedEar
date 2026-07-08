'use client'

import { useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { AudioLines, Sparkles, Music2, ArrowUpRight, Loader2 } from 'lucide-react';
import { AmbientMeter } from '@/components/ui/AmbientMeter';
import { API_BASE } from '@/lib/api-client';

const FEATURES = [
  { icon: Sparkles, text: 'Real recommendations from your actual listening data' },
  { icon: Music2, text: 'Genre, era, and popularity analysis — no fake stats' },
  { icon: ArrowUpRight, text: 'Export any generated playlist straight to Spotify' },
];

export default function LoginPage() {
  const [isLoading, setIsLoading] = useState(false);

  const handleSpotifyLogin = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`);
      const data = await response.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        setIsLoading(false);
      }
    } catch (error) {
      console.error('Login error:', error);
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-ink relative overflow-hidden flex flex-col">
      <div className="absolute inset-x-0 bottom-0 h-40 opacity-30 pointer-events-none">
        <AmbientMeter className="h-full px-8" />
      </div>

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 py-16">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-sm"
        >
          <div className="flex items-center justify-center gap-2.5 mb-8">
            <div className="w-10 h-10 rounded-xl bg-amber flex items-center justify-center">
              <AudioLines className="w-5 h-5 text-ink" strokeWidth={2.5} />
            </div>
            <span className="font-display font-bold text-2xl tracking-tight">BlessedEar</span>
          </div>

          <div className="text-center mb-8">
            <h1 className="font-display font-bold text-2xl mb-2">Connect your account</h1>
            <p className="text-bone-dim text-sm">
              We'll read your top tracks, saved songs, and playlists to build real recommendations.
            </p>
          </div>

          <div className="bg-panel border border-panel-border rounded-2xl p-5 mb-6 space-y-3.5">
            {FEATURES.map((feature, i) => (
              <div key={i} className="flex items-center gap-3 text-left">
                <feature.icon className="w-4 h-4 text-amber shrink-0" strokeWidth={2} />
                <span className="text-sm text-bone">{feature.text}</span>
              </div>
            ))}
          </div>

          <button
            onClick={handleSpotifyLogin}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 bg-amber text-ink font-display font-semibold py-3.5 rounded-xl shadow-glow hover:bg-amber-dim transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Connecting…
              </>
            ) : (
              <>
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.42 1.56-.299.421-1.02.599-1.559.3z" />
                </svg>
                Connect with Spotify
              </>
            )}
          </button>

          <div className="text-center mt-6">
            <Link href="/" className="text-sm text-bone-dim hover:text-bone transition-colors">
              ← Back to home
            </Link>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
