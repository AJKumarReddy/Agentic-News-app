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
        // Primary — indigo/violet
        brand: {
          50: '#f3f2ff',
          100: '#e7e4ff',
          200: '#d0caff',
          300: '#b0a5fc',
          400: '#8f7bf7',
          500: '#7355ee',
          600: '#5f3fd8',
          700: '#4d31b0',
          800: '#3a2686',
          900: '#281a5c',
          950: '#180f38',
        },
        // Secondary — teal, for supporting actions and highlights
        accent: {
          50: '#eefdfa',
          100: '#d3f8f1',
          200: '#a9efe5',
          300: '#71e0d3',
          400: '#38c8bb',
          500: '#18aca1',
          600: '#0e8a83',
          700: '#106e6a',
          800: '#125856',
          900: '#134949',
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
        ink: {
          50: '#f8f9fc',
          100: '#f1f2f8',
          200: '#e4e6f0',
          300: '#cbcfe0',
          400: '#979dba',
          500: '#6b7192',
          600: '#4c5273',
          700: '#363b57',
          800: '#23273c',
          900: '#151827',
        },
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #5f3fd8 0%, #7355ee 45%, #18aca1 100%)',
        'brand-soft': 'linear-gradient(180deg, #fbfbfd 0%, #f6f7fa 100%)',
        'sidebar-gradient': 'linear-gradient(175deg, #281a5c 0%, #180f38 55%, #134949 100%)',
        'brand-soft-dark': 'linear-gradient(135deg, #14121f 0%, #101a1e 100%)',
      },
      fontFamily: {
        serif: ['Georgia', 'Times New Roman', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(21, 24, 39, 0.04), 0 4px 16px rgba(21, 24, 39, 0.06)',
        lift: '0 2px 4px rgba(21, 24, 39, 0.06), 0 10px 24px rgba(21, 24, 39, 0.10)',
        glow: '0 8px 28px rgba(95, 63, 216, 0.28)',
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
      },
      animation: {
        'fade-up': 'fade-up 0.25s ease-out',
        shimmer: 'shimmer 1.4s linear infinite',
        'slide-in-left': 'slide-in-left 0.22s cubic-bezier(0.32, 0.72, 0, 1)',
        'fade-in': 'fade-in 0.2s ease-out',
        equalize: 'equalize 0.85s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
