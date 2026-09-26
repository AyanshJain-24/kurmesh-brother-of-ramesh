/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        kurmesh: {
          polar: "#F7FAFC",
          surface: "#FFFFFF",
          navy: "#0B3954",
          blue: "#087EA4",
          cyan: "#22B8CF",
          teal: "#159A9C",
          text: "#172B4D",
          muted: "#5B7083",
          border: "#D9E5EC",
          success: "#16855B",
          warning: "#C47A00",
          danger: "#C73E3E",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(11, 57, 84, 0.08)",
        panel: "0 4px 16px rgba(11, 57, 84, 0.08)",
      },
      borderRadius: {
        card: "12px",
      },
    },
  },
  plugins: [],
}
