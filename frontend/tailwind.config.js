/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        industrial: {
          950: '#0a0d12',
          900: '#10151f',
          850: '#151c2a',
          800: '#1b2436',
          700: '#2a374f',
          600: '#3f5070',
          accent: '#38bdf8',
          gold: '#f59e0b',
          emerald: '#10b981',
          danger: '#ef4444'
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace']
      }
    },
  },
  plugins: [],
}
