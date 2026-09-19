import type { Config } from "tailwindcss";

/**
 * Design tokens for the Adobe Stock AI Image Studio.
 *
 * The palette is derived from the two reference compositions in `REFERENCES/`:
 * a deep, desaturated navy surface family with a single bright cyan/turquoise
 * accent. Neutrals are deliberately blue-tinted (never pure grey) so panels
 * read as part of one continuous surface rather than stacked boxes.
 */
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        /** Surface scale: 950 = page backdrop, 800/750 = panels, 100/50 = text. */
        navy: {
          950: "#050F1C",
          900: "#08182A",
          850: "#0B2035",
          800: "#0F2A42",
          750: "#143350",
          700: "#1A3E5E",
          600: "#245176",
          500: "#326A94",
          400: "#4E8BB4",
          300: "#7FAECF",
          200: "#AECBE2",
          100: "#DCE9F4",
          50: "#F2F8FD",
        },
        /** Signature accent — the cyan from both reference images. */
        accent: {
          900: "#0A3A47",
          800: "#0E5568",
          700: "#137589",
          600: "#1997AF",
          500: "#2FB9D6",
          400: "#45CEE8",
          300: "#7FE2F2",
          200: "#B3EFF9",
          100: "#DEF8FD",
        },
        /** QC verdict palette (kept from the previous theme for continuity). */
        status: {
          pending: "#7FAECF",
          auditing: "#AECBE2",
          passed: "#34D399",
          flagged: "#FBBF24",
          approved: "#A78BFA",
          ready: "#2FB9D6",
        },
      },
      boxShadow: {
        panel: "inset 0 1px 0 0 rgba(255,255,255,0.04), 0 24px 48px -32px rgba(0,0,0,0.95)",
        raised: "0 18px 36px -24px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(47,185,214,0.28), 0 14px 44px -14px rgba(47,185,214,0.5)",
        "glow-sm": "0 0 0 1px rgba(47,185,214,0.22), 0 8px 24px -10px rgba(47,185,214,0.42)",
      },
      backgroundImage: {
        /** Ambient wash used on page shells — the reference's soft focal glow. */
        "ambient-glow":
          "radial-gradient(1200px 620px at 12% -12%, rgba(47,185,214,0.16), transparent 62%), radial-gradient(900px 520px at 92% 4%, rgba(36,81,118,0.22), transparent 60%)",
        "panel-sheen":
          "linear-gradient(160deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0) 46%)",
        "accent-sheen": "linear-gradient(135deg, #45CEE8 0%, #1997AF 100%)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 240ms ease-out both",
        "pulse-ring": "pulse-ring 1.8s ease-in-out infinite",
      },
      transitionTimingFunction: {
        swift: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
