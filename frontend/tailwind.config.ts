import type { Config } from "tailwindcss";

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
        status: {
          pending: "#71717a",
          auditing: "#a1a1aa",
          passed: "#10b981",
          flagged: "#f59e0b",
          approved: "#8b5cf6",
          ready: "#3b82f6",
        },
      },
    },
  },
  plugins: [],
};

export default config;
