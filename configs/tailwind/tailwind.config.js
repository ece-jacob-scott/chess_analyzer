const plugin = require("tailwindcss/plugin");

module.exports = {
  content: [
    "./chess_analyzer/templates/**/*.html.*",
    "./chess_analyzer/templates/**/*.html",
    "./chess_analyzer/templates/*.html",
  ],
  theme: {
    extend: {},
  },
  plugins: [
    plugin(function ({ addVariant }) {
      addVariant("htmx-settling", ["&.htmx-settling", ".htmx-settling &"]);
      addVariant("htmx-request", ["&.htmx-request", ".htmx-request &"]);
      addVariant("htmx-swapping", ["&.htmx-swapping", ".htmx-swapping &"]);
      addVariant("htmx-added", ["&.htmx-added", ".htmx-added &"]);
    }),
  ],
};
