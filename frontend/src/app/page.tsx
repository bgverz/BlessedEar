'use client'

import Link from 'next/link';
import { motion } from 'framer-motion';
import { AudioLines, ArrowRight } from 'lucide-react';
import { AmbientMeter } from '@/components/ui/AmbientMeter';

const STEPS = [
  { n: '01', title: 'Connect', body: 'Link your Spotify account — nothing to configure, no forms to fill out.' },
  { n: '02', title: 'Analyze', body: 'We read your real top tracks, saved songs, and playlists — genres, eras, popularity.' },
  { n: '03', title: 'Discover', body: 'Get deep cuts from artists you already love, plus genres you haven’t tried yet.' },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-ink overflow-hidden">
      <header className="flex items-center justify-between px-6 sm:px-10 py-6 max-w-6xl mx-auto">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-amber flex items-center justify-center">
            <AudioLines className="w-4.5 h-4.5 text-ink" strokeWidth={2.5} />
          </div>
          <span className="font-display font-bold text-lg tracking-tight">BlessedEar</span>
        </div>
        <Link
          href="/login"
          className="text-sm font-medium text-bone-dim hover:text-bone transition-colors"
        >
          Sign in
        </Link>
      </header>

      <section className="max-w-6xl mx-auto px-6 sm:px-10 pt-16 sm:pt-24 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-2xl"
        >
          <h1 className="font-display font-bold text-4xl sm:text-6xl leading-[1.05] tracking-tight">
            Music discovery, <span className="text-amber">read from your own signal.</span>
          </h1>
          <p className="text-bone-dim text-lg mt-6 max-w-xl">
            No generic charts, no guesswork. BlessedEar analyzes what you actually listen to
            and surfaces the tracks your library is already pointing toward.
          </p>
          <div className="flex items-center gap-4 mt-9">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 bg-amber text-ink font-display font-semibold px-6 py-3.5 rounded-xl shadow-glow hover:bg-amber-dim transition-colors"
            >
              Connect with Spotify
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mt-20 h-24 sm:h-32"
        >
          <AmbientMeter className="h-full" />
        </motion.div>
      </section>

      <section className="max-w-6xl mx-auto px-6 sm:px-10 pb-24">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {STEPS.map((step, i) => (
            <motion.div
              key={step.n}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className="bg-panel border border-panel-border rounded-2xl p-6"
            >
              <span className="font-mono text-xs text-amber">{step.n}</span>
              <h3 className="font-display font-semibold text-lg mt-2 mb-2">{step.title}</h3>
              <p className="text-sm text-bone-dim">{step.body}</p>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}
