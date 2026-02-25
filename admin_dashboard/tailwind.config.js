/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        darkTeal: '#0B2027',
        mediumBlue: '#40798C',
        mutedTeal: '#70A9A1',
        lightGrey: '#CFD7C7',
        lightCream: '#F6F1D1',
        pageBg: '#F5F5F5',
        primary: {
          50: '#F6F1D1',
          100: '#CFD7C7',
          200: '#70A9A1',
          300: '#4079BC',
          400: '#0B2027',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
        },
      },
    },
  },
  plugins: [],
}

