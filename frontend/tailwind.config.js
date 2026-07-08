/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // "Channel strip" palette — warm analog-console tones instead of
        // neutral gray-900 + Spotify green.
        ink: {
          DEFAULT: '#15131A',
          light: '#1B1822',
        },
        panel: {
          DEFAULT: '#211E29',
          light: '#2C2836',
          border: '#38333F',
        },
        bone: {
          DEFAULT: '#F2EDE4',
          dim: '#B8B2C4',
        },
        amber: {
          DEFAULT: '#E8A33D',
          dim: '#B87F2E',
        },
        coral: {
          DEFAULT: '#E85C4A',
          dim: '#B4483A',
        },
        violet: {
          DEFAULT: '#8B7FD9',
          dim: '#6C61AD',
        },
      },
      fontFamily: {
        display: ['var(--font-display)', 'system-ui', 'sans-serif'],
        body: ['var(--font-body)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      animation: {
        'meter-rise': 'meterRise 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-in': 'fadeIn 0.5s ease-out forwards',
        'slide-up': 'slideUp 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'scale-in': 'scaleIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards',
      },
      keyframes: {
        meterRise: {
          '0%': { transform: 'scaleY(0)' },
          '100%': { transform: 'scaleY(1)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(14px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.96)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(242, 237, 228, 0.04) inset, 0 8px 24px -8px rgba(0, 0, 0, 0.5)',
        glow: '0 0 24px -4px rgba(232, 163, 61, 0.35)',
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.25rem',
      },
    },
  },
  plugins: [],
}
