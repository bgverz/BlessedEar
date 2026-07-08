'use client'

import { motion } from 'framer-motion';

/** Ambient pulsing meter used in place of a generic spinner for loading states */
export function LoadingMeter({ label }: { label?: string }) {
  const bars = [0.4, 0.9, 0.6, 1, 0.5, 0.75];
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10">
      <div className="flex items-end gap-1 h-8">
        {bars.map((h, i) => (
          <motion.div
            key={i}
            className="w-1.5 bg-amber rounded-full"
            animate={{ scaleY: [0.3, h, 0.3] }}
            transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.1, ease: 'easeInOut' }}
            style={{ height: '100%', transformOrigin: 'bottom' }}
          />
        ))}
      </div>
      {label && <p className="text-sm text-bone-dim">{label}</p>}
    </div>
  );
}
