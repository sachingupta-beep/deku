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
        primary: '#4F46E5',
        'primary-hover': '#4338CA',
        border: '#E5E7EB',
        danger: '#DC2626',
        success: '#16A34A',
        muted: '#6B7280',
        'habit-indigo': '#4F46E5',
        'habit-teal': '#0D9488',
        'habit-amber': '#D97706',
        'habit-rose': '#E11D48',
        'habit-slate': '#475569',
        'habit-forest': '#166534',
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
