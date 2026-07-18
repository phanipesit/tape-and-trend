/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,jsx}", "./components/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0E14", panel: "#121722", panel2: "#0F1420",
        line: "#1E2634", line2: "#2A3448",
        txt: "#E8ECF4", mut: "#8A94A6", dim: "#5A6478",
        brass: "#F5B942", up: "#2ED47E", down: "#FF5C5C", info: "#4DA3FF",
      },
      fontFamily: { mono: ["IBM Plex Mono", "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
};
