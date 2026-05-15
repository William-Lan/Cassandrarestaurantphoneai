/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fef3f2',
          100: '#fee4e2',
          500: '#e84b3a',
          600: '#c93528',
          700: '#a5281d',
        },
      },
    },
  },
  plugins: [],
}
