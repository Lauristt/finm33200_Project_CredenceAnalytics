import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#FAFAF7",
        border: "#EAEAE5",
        "border-hover": "#D8D8D2",
        accent: "#1B3A57",
        "conf-green": "#2F7D5B",
        "conf-amber": "#B8923A",
        "conf-orange": "#C2602E",
        "conf-red": "#A4332B",
        "subtle": "#F7F6F1",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
      fontSize: {
        "2xs": ["11px", { lineHeight: "1.4", letterSpacing: "0.05em" }],
        xs: ["13px", { lineHeight: "1.5" }],
        sm: ["14px", { lineHeight: "1.55" }],
        base: ["15px", { lineHeight: "1.55" }],
        lg: ["17px", { lineHeight: "1.4" }],
        xl: ["19px", { lineHeight: "1.3" }],
        "2xl": ["22px", { lineHeight: "1.25" }],
        "3xl": ["28px", { lineHeight: "1.2" }],
        "4xl": ["36px", { lineHeight: "1" }],
      },
      borderRadius: {
        DEFAULT: "6px",
        md: "6px",
        lg: "10px",
        full: "9999px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
