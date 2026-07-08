'use client'

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import toast from 'react-hot-toast';
import { Button } from '@/components/ui/Button';
import { savePlaylist, RecommendationTrack } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';

export function SavePlaylistModal({
  isOpen,
  onClose,
  tracks,
  defaultName,
  mood,
}: {
  isOpen: boolean;
  onClose: () => void;
  tracks: RecommendationTrack[];
  defaultName: string;
  mood?: string | null;
}) {
  const { token } = useAuth();
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!token || !name.trim()) return;
    setIsSaving(true);
    try {
      await savePlaylist(token, {
        name: name.trim(),
        description: description.trim() || undefined,
        tracks,
        mood: mood || null,
        generation_type: mood ? 'mood' : 'recommendation',
      });
      toast.success('Playlist saved');
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save playlist');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-ink/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          onClick={(e) => e.stopPropagation()}
          className="bg-panel border border-panel-border rounded-2xl p-6 w-full max-w-md"
        >
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-display font-semibold text-lg">Save playlist</h3>
            <button onClick={onClose} className="text-bone-dim hover:text-bone">
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label className="text-xs text-bone-dim mb-1.5 block">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter playlist name"
                className="w-full bg-ink border border-panel-border rounded-xl px-3.5 py-2.5 text-sm text-bone placeholder:text-bone-dim/60 focus:border-amber outline-none transition-colors"
              />
            </div>
            <div>
              <label className="text-xs text-bone-dim mb-1.5 block">Description (optional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Enter description"
                rows={3}
                className="w-full bg-ink border border-panel-border rounded-xl px-3.5 py-2.5 text-sm text-bone placeholder:text-bone-dim/60 focus:border-amber outline-none transition-colors resize-none"
              />
            </div>
            <p className="text-xs text-bone-dim">{tracks.length} tracks</p>
          </div>

          <div className="flex gap-3 mt-6">
            <Button variant="secondary" onClick={onClose} className="flex-1">
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving || !name.trim()} className="flex-1">
              {isSaving ? 'Saving…' : 'Save playlist'}
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
