/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#FAF9F7',
        surface: '#FFFFFF',
        primary: {
          DEFAULT: '#4F46E5',
          hover: '#4338CA',
        },
        muted: '#6B7280',
        border: '#E5E7EB',
        danger: '#DC2626',
        success: '#16A34A',
        habit: {
          indigo: '#4F46E5',
          teal: '#0D9488',
          amber: '#D97706',
          rose: '#E11D48',
          slate: '#475569',
          forest: '#166534',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '8px',
        card: '12px',
      },
    },
  },
  plugins: [],
}
