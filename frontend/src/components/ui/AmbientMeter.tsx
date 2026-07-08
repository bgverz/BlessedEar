'use client'

import { motion } from 'framer-motion';

const HEIGHTS = [0.3, 0.55, 0.8, 0.45, 0.95, 0.6, 0.35, 0.75, 0.5, 0.9, 0.4, 0.65, 0.85, 0.3, 0.7, 0.5, 0.8, 0.35, 0.6, 0.45];
const COLORS = ['bg-amber', 'bg-coral', 'bg-violet'];

/** Full-width ambient level meter used as hero decoration on landing/login */
export function AmbientMeter({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-end gap-1.5 ${className}`} aria-hidden="true">
      {HEIGHTS.map((h, i) => (
        <motion.div
          key={i}
          initial={{ scaleY: 0 }}
          animate={{ scaleY: [0.4, h, 0.5, h * 0.8, h] }}
          transition={{
            scaleY: {
              duration: 2.4 + (i % 5) * 0.3,
              repeat: Infinity,
              repeatType: 'mirror',
              ease: 'easeInOut',
              delay: i * 0.06,
            },
          }}
          className={`flex-1 rounded-full ${COLORS[i % COLORS.length]} opacity-70`}
          style={{ height: '100%', transformOrigin: 'bottom' }}
        />
      ))}
    </div>
  );
}
