import type { Config } from "tailwindcss";

/**
 * Design tokens for the vintage batch studio.
 *
 * Direction: aged-paper surfaces, ink-brown type, brass/oxblood accents —
 * inspired by the "Antiques" reference (parchment, serif display, ticket
 * cards, stamps). Everything is warm; there are no blue-tinted neutrals.
 */
const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /** Parchment page backdrop: 50 = freshest sheet, 900 = deep stain. */
        parchment: {
          50: "#fbf6ea",
          100: "#f7f0df",
          200: "#efe6cf",
          300: "#e4d8ba",
          400: "#d6c69f",
          500: "#c4b083",
          600: "#ad9563",
          700: "#8f774c",
          800: "#6f5a3a",
          900: "#4c3d28",
        },
        /** Ink: primary type + line work. */
        ink: {
          50: "#f4efe7",
          200: "#c9bda9",
          400: "#7d705c",
          600: "#4a412f",
          800: "#2f281c",
          900: "#1e1912",
        },
        /** Brass: gilded accents, rules, badges. */
        brass: {
          300: "#d9bd7e",
          400: "#c9a757",
          500: "#a98541",
          600: "#8a6a2f",
          700: "#6b5123",
        },
        /** Oxblood: primary actions (the reference's red wax seal). */
        oxblood: {
          400: "#b2564a",
          500: "#8b3a2f",
          600: "#742f26",
          700: "#5c251e",
        },
        /** Olive: success / passed states. */
        olive: {
          400: "#7d8a4f",
          500: "#5b6334",
          600: "#4a5129",
        },
        /** Rust: warnings + failures. */
        rust: {
          400: "#c07a3a",
          500: "#a15f26",
          600: "#824a1c",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "Georgia", "serif"],
        stamp: ["var(--font-stamp)", "Courier New", "monospace"],
        script: ["var(--font-script)", "cursive"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(76, 61, 40, 0.10), 0 8px 24px -16px rgba(76, 61, 40, 0.35)",
        raised: "0 2px 4px rgba(76, 61, 40, 0.12), 0 16px 40px -20px rgba(76, 61, 40, 0.45)",
        seal: "inset 0 0 0 1px rgba(169, 133, 65, 0.35)",
      },
      backgroundImage: {
        "paper-grain": "url('/grain.svg')",
        "aged-vignette":
          "radial-gradient(ellipse at 50% 0%, rgba(255,252,244,0.55), transparent 55%), radial-gradient(ellipse at 50% 100%, rgba(76,61,40,0.10), transparent 60%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "stamp-in": {
          "0%": { opacity: "0", transform: "scale(1.15) rotate(-6deg)" },
          "100%": { opacity: "1", transform: "scale(1) rotate(-2deg)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s ease-out both",
        "stamp-in": "stamp-in 0.35s cubic-bezier(0.2, 0.9, 0.3, 1.4) both",
      },
    },
  },
  plugins: [],
};

export default config;
