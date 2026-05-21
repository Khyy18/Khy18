/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        'tg-bg': 'var(--tg-theme-bg-color)',
        'tg-text': 'var(--tg-theme-text-color)',
        'tg-button': 'var(--tg-theme-button-color)',
        'tg-hint': 'var(--tg-theme-hint-color)',
        'tg-secondary-bg': 'var(--tg-theme-secondary-bg-color)',
      },
    },
  },
  plugins: [],
};
