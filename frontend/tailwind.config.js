/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Editorial indigo — publisher-neutral, since the app now spans
        // multiple newsrooms rather than one masthead
        brand: {
          50: '#f2f4ff',
          100: '#e3e7fe',
          200: '#c8cffd',
          300: '#a3adf9',
          400: '#7c83f2',
          500: '#5b5be6',
          600: '#4842cc',
          700: '#3a35a4',
          800: '#2c2a7a',
          900: '#1e1c52',
          950: '#12102f',
        },
        // per-publisher accents used on source badges
        guardian: '#0b5394',
        nyt: '#1a1a1a',
        ink: {
          50: '#f8f9fb',
          100: '#f1f3f7',
          200: '#e4e7ee',
          300: '#cbd1dd',
          400: '#98a1b5',
          500: '#6b7488',
          600: '#4c5566',
          700: '#363d4b',
          800: '#232936',
          900: '#151a24',
        },
      },
      fontFamily: {
        serif: ['Georgia', 'Times New Roman', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(21, 26, 36, 0.04), 0 4px 16px rgba(21, 26, 36, 0.06)',
        lift: '0 2px 4px rgba(21, 26, 36, 0.06), 0 12px 32px rgba(21, 26, 36, 0.10)',
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
      },
      animation: {
        'fade-up': 'fade-up 0.25s ease-out',
        shimmer: 'shimmer 1.4s linear infinite',
      },
    },
  },
  plugins: [],
};
