'use client'

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { RecommendationTrack } from './api-client';

interface PlayerContextValue {
  currentTrack: RecommendationTrack | null;
  isPlaying: boolean;
  progress: number; // 0-1
  toggle: (track: RecommendationTrack) => void;
  stop: () => void;
}

const PlayerContext = createContext<PlayerContextValue | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [currentTrack, setCurrentTrack] = useState<RecommendationTrack | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;

    const onTimeUpdate = () => {
      if (audio.duration) setProgress(audio.currentTime / audio.duration);
    };
    const onEnded = () => {
      setIsPlaying(false);
      setProgress(0);
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('pause', () => setIsPlaying(false));
    audio.addEventListener('play', () => setIsPlaying(true));

    return () => {
      audio.pause();
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('ended', onEnded);
    };
  }, []);

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    setCurrentTrack(null);
    setIsPlaying(false);
    setProgress(0);
  }, []);

  const toggle = useCallback(
    (track: RecommendationTrack) => {
      const audio = audioRef.current;
      if (!audio || !track.preview_url) return;

      if (currentTrack?.id === track.id) {
        if (audio.paused) {
          audio.play();
        } else {
          audio.pause();
        }
        return;
      }

      audio.src = track.preview_url;
      audio.currentTime = 0;
      setCurrentTrack(track);
      setProgress(0);
      audio.play();
    },
    [currentTrack]
  );

  return (
    <PlayerContext.Provider value={{ currentTrack, isPlaying, progress, toggle, stop }}>
      {children}
    </PlayerContext.Provider>
  );
}

export function usePlayer() {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error('usePlayer must be used within PlayerProvider');
  return ctx;
}
