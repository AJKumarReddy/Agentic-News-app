/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4fb',
          100: '#d8e6f6',
          500: '#0f6bb5',
          600: '#0b5394',
          700: '#083d6e',
          800: '#063057',
          900: '#052962',
        },
      },
      fontFamily: {
        serif: ['Georgia', 'Times New Roman', 'serif'],
      },
    },
  },
  plugins: [],
};
