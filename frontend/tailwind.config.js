/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas:  '#0A1628',
        surface: '#0F2040',
        raised:  '#162A52',
        border:  '#1B3A6B',
        gold:    '#D4A017',
        goldlt:  '#E8C547',
        gain:    '#1BCA8A',
        gainbg:  '#0D2E21',
        loss:    '#E84848',
        lossbg:  '#2E0F0F',
        muted:   '#8899BB',
        text:    '#E8EDF5',
      },
      fontFamily: {
        display: ['"DM Serif Display"', 'serif'],
        body:    ['Inter', 'sans-serif'],
        data:    ['"JetBrains Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
}
