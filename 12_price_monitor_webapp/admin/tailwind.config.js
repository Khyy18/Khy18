/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: '#FF6B35',
        'accent-dark': '#E55A2B',
        'accent-light': '#FF8F66',
      },
    },
  },
  plugins: [],
};
