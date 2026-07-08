'use client'

import { AnimatePresence, motion } from 'framer-motion';
import { Play, Pause, X, Music2 } from 'lucide-react';
import { usePlayer } from '@/lib/player-context';

export function NowPlayingBar() {
  const { currentTrack, isPlaying, progress, toggle, stop } = usePlayer();

  return (
    <AnimatePresence>
      {currentTrack && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="fixed bottom-0 left-0 right-0 h-20 bg-panel border-t border-panel-border z-40 flex items-center px-5 gap-4"
        >
          <div className="w-11 h-11 rounded-lg bg-panel-light overflow-hidden shrink-0 flex items-center justify-center">
            {currentTrack.album_images?.[currentTrack.album_images.length - 1]?.url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={currentTrack.album_images[currentTrack.album_images.length - 1].url}
                alt={currentTrack.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <Music2 className="w-4 h-4 text-bone-dim" />
            )}
          </div>

          <div className="min-w-0 w-48 shrink-0">
            <p className="text-sm font-medium truncate">{currentTrack.name}</p>
            <p className="text-xs text-bone-dim truncate">{currentTrack.artists.join(', ')}</p>
          </div>

          <button
            onClick={() => toggle(currentTrack)}
            className="w-9 h-9 rounded-full bg-amber text-ink flex items-center justify-center shrink-0 hover:bg-amber-dim transition-colors"
          >
            {isPlaying ? <Pause className="w-4 h-4" fill="currentColor" /> : <Play className="w-4 h-4 ml-0.5" fill="currentColor" />}
          </button>

          <div className="flex-1 h-1.5 bg-panel-light rounded-full overflow-hidden max-w-md">
            <motion.div
              className="h-full bg-amber rounded-full"
              style={{ width: `${Math.min(progress * 100, 100)}%` }}
              transition={{ ease: 'linear' }}
            />
          </div>

          <span className="text-xs text-bone-dim font-mono w-16 text-right shrink-0 hidden sm:block">
            preview
          </span>

          <button
            onClick={stop}
            className="w-8 h-8 rounded-full flex items-center justify-center text-bone-dim hover:text-bone hover:bg-panel-light transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
