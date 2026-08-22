/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  // hover: variants compile inside @media (hover: hover) — on touch devices a tap
  // no longer latches a hover state that only a second tap elsewhere clears
  future: { hoverOnlyWhenSupported: true },
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Primary — SOURCE blue. #2563EB is the brand Primary, so it sits
        // at 600 where the app already reaches for its main action colour.
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
          950: '#172554',
        },
        // Secondary — SOURCE cyan (#06B6D4 at 500), for supporting accents
        accent: {
          50: '#ecfeff',
          100: '#cffafe',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
        },
        // Warm accent — used for web sources and emphasis
        warm: {
          50: '#fff6ed',
          100: '#ffead4',
          200: '#fdd2a8',
          300: '#fbb271',
          400: '#f98938',
          500: '#f76b12',
          600: '#e85108',
          700: '#c03b09',
          800: '#983010',
          900: '#7a2a10',
        },
        // per-publisher accents
        guardian: '#0b5394',
        nyt: '#1a1a1a',
        // Neutrals, tilted navy so the dark surfaces land on Midnight
        // rather than the old violet-grey. 50 is the sheet's Background.
        ink: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#1e293b',
          800: '#122145',
          900: '#0b1b44',
        },
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #2563eb 0%, #3b82f6 45%, #06b6d4 100%)',
        'brand-soft': 'linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%)',
        'sidebar-gradient': 'linear-gradient(175deg, #12275e 0%, #0b1b44 55%, #0e7490 100%)',
        'brand-soft-dark': 'linear-gradient(135deg, #0b1b44 0%, #08182f 100%)',
      },
      fontFamily: {
        serif: ['Georgia', 'Times New Roman', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(21, 24, 39, 0.04), 0 4px 16px rgba(21, 24, 39, 0.06)',
        lift: '0 2px 4px rgba(21, 24, 39, 0.06), 0 10px 24px rgba(21, 24, 39, 0.10)',
        glow: '0 8px 28px rgba(37, 99, 235, 0.28)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-500px 0' },
          '100%': { backgroundPosition: '500px 0' },
        },
        'slide-in-left': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        'slide-in-right': {
          '0%': { transform: 'translateX(100%)' },
          '100%': { transform: 'translateX(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        // voice playback: bars scale from their own centre, so each rect needs
        // transform-box: fill-box — set inline in VoiceIcon
        equalize: {
          '0%, 100%': { transform: 'scaleY(0.3)' },
          '50%': { transform: 'scaleY(1)' },
        },
        // Sage's thinking dots: opacity only, so the dots stay put rather than
        // jittering the visor they sit on
        'sage-dot': {
          '0%, 100%': { opacity: '0.25' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.25s ease-out',
        shimmer: 'shimmer 1.4s linear infinite',
        'slide-in-left': 'slide-in-left 0.22s cubic-bezier(0.32, 0.72, 0, 1)',
        'slide-in-right': 'slide-in-right 0.22s cubic-bezier(0.32, 0.72, 0, 1)',
        'fade-in': 'fade-in 0.2s ease-out',
        equalize: 'equalize 0.85s ease-in-out infinite',
        'sage-dot': 'sage-dot 1.1s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
