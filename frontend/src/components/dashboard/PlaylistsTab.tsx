'use client'

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ExternalLink, Trash2, Upload, X, ListMusic } from 'lucide-react';
import toast from 'react-hot-toast';
import { Panel } from '@/components/ui/Panel';
import { Button } from '@/components/ui/Button';
import { LoadingMeter } from '@/components/ui/LoadingMeter';
import { useAuth } from '@/lib/auth-context';
import {
  getMyPlaylists,
  getPlaylistDetails,
  deletePlaylist,
  exportPlaylistToSpotify,
  SavedPlaylist,
  RecommendationTrack,
  UnauthorizedError,
} from '@/lib/api-client';

export function PlaylistsTab() {
  const { token } = useAuth();
  const [playlists, setPlaylists] = useState<SavedPlaylist[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selected, setSelected] = useState<{ playlist: SavedPlaylist; tracks: RecommendationTrack[] } | null>(null);
  const [exportTarget, setExportTarget] = useState<SavedPlaylist | null>(null);

  const load = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const data = await getMyPlaylists(token);
      setPlaylists(data);
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error('Could not load playlists');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const openDetails = async (playlist: SavedPlaylist) => {
    if (!token) return;
    try {
      const details = await getPlaylistDetails(token, playlist.id);
      setSelected({ playlist, tracks: details.tracks || [] });
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error('Could not load playlist');
    }
  };

  const handleDelete = async (playlist: SavedPlaylist, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!token) return;
    try {
      await deletePlaylist(token, playlist.id);
      setPlaylists((prev) => prev.filter((p) => p.id !== playlist.id));
      toast.success('Playlist deleted');
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error('Could not delete playlist');
    }
  };

  const handleExport = async () => {
    if (!token || !exportTarget) return;
    try {
      const result = await exportPlaylistToSpotify(token, exportTarget.id);
      toast.success('Exported to Spotify');
      setPlaylists((prev) =>
        prev.map((p) => (p.id === exportTarget.id ? { ...p, is_exported: true, spotify_playlist_id: result.spotify_playlist_id } : p))
      );
      setExportTarget(null);
      if (result.spotify_url) window.open(result.spotify_url, '_blank');
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error('Export failed');
    }
  };

  if (isLoading) return <LoadingMeter label="Loading playlists…" />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-3xl sm:text-4xl tracking-tight">Playlists</h1>
        <p className="text-bone-dim text-sm mt-1">Playlists you've saved from recommendations and discovery.</p>
      </div>

      {playlists.length === 0 ? (
        <Panel className="text-center py-12">
          <ListMusic className="w-8 h-8 text-bone-dim mx-auto mb-3" />
          <p className="text-bone-dim">No saved playlists yet — generate some recommendations and save them.</p>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {playlists.map((playlist) => (
            <motion.div
              key={playlist.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => openDetails(playlist)}
              className="bg-panel border border-panel-border rounded-2xl p-5 cursor-pointer hover:border-amber/40 transition-colors flex flex-col gap-3"
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <p className="font-display font-semibold truncate">{playlist.name}</p>
                  <p className="text-xs text-bone-dim mt-0.5">{playlist.track_count} tracks</p>
                </div>
                {playlist.is_exported && <span className="text-[10px] uppercase tracking-wide text-amber shrink-0">Exported</span>}
              </div>
              {playlist.description && <p className="text-xs text-bone-dim line-clamp-2">{playlist.description}</p>}
              <div className="flex gap-2 mt-auto pt-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setExportTarget(playlist);
                  }}
                  className="flex items-center gap-1.5 text-xs text-bone-dim hover:text-amber transition-colors"
                >
                  <Upload className="w-3.5 h-3.5" /> Export
                </button>
                <button
                  onClick={(e) => handleDelete(playlist, e)}
                  className="flex items-center gap-1.5 text-xs text-bone-dim hover:text-coral transition-colors ml-auto"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Delete
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-ink/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setSelected(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-panel border border-panel-border rounded-2xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display font-semibold text-lg">{selected.playlist.name}</h3>
                <button onClick={() => setSelected(null)} className="text-bone-dim hover:text-bone">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="space-y-1.5">
                {selected.tracks.map((track, i) => (
                  <div key={track.id || i} className="flex items-center gap-3 p-2 rounded-lg hover:bg-panel-light">
                    <span className="w-5 text-center text-xs font-mono text-bone-dim">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm truncate">{track.name}</p>
                      <p className="text-xs text-bone-dim truncate">{track.artists?.join(', ')}</p>
                    </div>
                    {track.external_urls?.spotify && (
                      <a href={track.external_urls.spotify} target="_blank" rel="noopener noreferrer" className="text-bone-dim hover:text-amber">
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {exportTarget && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-ink/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setExportTarget(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-panel border border-panel-border rounded-2xl p-6 w-full max-w-sm"
            >
              <h3 className="font-display font-semibold text-lg mb-2">Export to Spotify</h3>
              <p className="text-sm text-bone-dim mb-6">
                Create &ldquo;{exportTarget.name}&rdquo; as a private playlist in your Spotify account.
              </p>
              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => setExportTarget(null)} className="flex-1">
                  Cancel
                </Button>
                <Button onClick={handleExport} className="flex-1">
                  Export
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
