'use client'

import { motion } from 'framer-motion';

interface MeterProps {
  value: number; // 0-1
  color?: 'amber' | 'coral' | 'violet';
  segments?: number;
  label?: string;
  valueLabel?: string;
  className?: string;
  delay?: number;
}

const COLOR_CLASSES: Record<NonNullable<MeterProps['color']>, string> = {
  amber: 'bg-amber',
  coral: 'bg-coral',
  violet: 'bg-violet',
};

/**
 * The recurring "level meter" motif — a segmented bar echoing an analog
 * VU/peak meter. Used both decoratively (hero, loading states) and
 * functionally (genre breakdown, popularity gauge, similarity score).
 */
export function Meter({ value, color = 'amber', segments = 14, label, valueLabel, className = '', delay = 0 }: MeterProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const activeSegments = Math.round(clamped * segments);
  const colorClass = COLOR_CLASSES[color];

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {(label || valueLabel) && (
        <div className="flex items-center justify-between text-xs">
          {label && <span className="text-bone-dim">{label}</span>}
          {valueLabel && <span className="text-bone font-mono tabular-nums">{valueLabel}</span>}
        </div>
      )}
      <div className="flex gap-[3px] h-2">
        {Array.from({ length: segments }).map((_, i) => (
          <motion.div
            key={i}
            initial={{ scaleY: 0 }}
            animate={{ scaleY: 1 }}
            transition={{ duration: 0.35, delay: delay + i * 0.015, ease: [0.16, 1, 0.3, 1] }}
            className={`flex-1 rounded-[2px] origin-bottom ${i < activeSegments ? colorClass : 'bg-panel-border'}`}
          />
        ))}
      </div>
    </div>
  );
}
