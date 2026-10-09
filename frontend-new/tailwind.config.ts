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
        /**
         * Leather surfaces (mapped by role, dark theme):
         * 50 = card sheet, 100 = deep page, 200/300 = raised hover + inset
         * states, 400/500 = hairline borders, 600+ = decorative glyph tones.
         */
        parchment: {
          50: "#2b2119",
          100: "#201812",
          200: "#362a20",
          300: "#423427",
          400: "#4f3f2e",
          500: "#6b563e",
          600: "#8a7050",
          700: "#a58a64",
          800: "#c0a57c",
          900: "#d8c39a",
        },
        /**
         * Ink: type tones for dark surfaces. Brighter = more prominent
         * (400 muted < 600 secondary < 800 primary). 900 is reserved for
         * scrims/selection and intentionally stays near-black.
         */
        ink: {
          50: "#f7efdd",
          200: "#d8c9ae",
          400: "#a29175",
          600: "#c9b993",
          800: "#eee3cc",
          900: "#17110a",
        },
        /** Brass: gilded accents, rules, badges. */
        brass: {
          300: "#ddc284",
          400: "#cba857",
          500: "#a98541",
          600: "#8a6a2f",
          700: "#6b5123",
        },
        /** Oxblood: primary actions (red wax seal). 400 = legible text tone. */
        oxblood: {
          300: "#e09a8f",
          400: "#d2796a",
          500: "#8b3a2f",
          600: "#742f26",
          700: "#5c251e",
        },
        /** Olive: success / passed states. 400 = legible text tone. */
        olive: {
          400: "#9db066",
          500: "#5b6334",
          600: "#4a5129",
        },
        /** Rust: warnings + failures. 400 = legible text tone. */
        rust: {
          400: "#dd9d5c",
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
        card: "0 1px 2px rgba(0, 0, 0, 0.45), 0 8px 24px -16px rgba(0, 0, 0, 0.7)",
        raised: "0 2px 4px rgba(0, 0, 0, 0.5), 0 16px 40px -20px rgba(0, 0, 0, 0.8)",
        seal: "inset 0 0 0 1px rgba(203, 168, 87, 0.35)",
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
