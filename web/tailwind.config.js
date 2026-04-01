/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0f0f1a",
        card: "#16162a",
        border: "#2a2a45",
        accent: "#7c3aed",
        "accent-light": "#a78bfa",
        muted: "#6b7280",
        zeta: "#3b82f6",
        crack: "#10b981",
        rofan: "#f59e0b",
      },
    },
  },
  plugins: [],
};
