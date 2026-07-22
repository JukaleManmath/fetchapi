import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#FFFFFF",
        ink: "#09090B",
        "ink-2": "#3F3F46",
        "ink-3": "#71717A",
        "ink-4": "#A1A1AA",
        "surface-1": "#FAFAFA",
        "surface-2": "#F4F4F5",
        "surface-3": "#E4E4E7",
        "border-1": "#E4E4E7",
        "border-2": "#D4D4D8",
        "border-3": "#A1A1AA",
      },
      fontFamily: {
        display: ["Playfair Display", "Georgia", "serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["10px", "14px"],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
      },
      boxShadow: {
        "card-sm": "0 1px 2px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.08)",
        card: "0 2px 8px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.06)",
        "card-lg": "0 8px 32px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,0,0,0.06)",
        "card-hover": "0 12px 40px rgba(0,0,0,0.16), 0 0 0 1px rgba(0,0,0,0.10)",
        "ink-glow": "0 0 0 3px rgba(9,9,11,0.12)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "perspective(800px) rotateX(12deg) translateY(24px)" },
          to: { opacity: "1", transform: "perspective(800px) rotateX(0deg) translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in-left": {
          from: { opacity: "0", transform: "translateX(-16px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.96)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          from: { backgroundPosition: "-200% 0" },
          to: { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16,1,0.3,1) forwards",
        "fade-in": "fade-in 0.3s ease-out forwards",
        "slide-in-left": "slide-in-left 0.3s cubic-bezier(0.16,1,0.3,1) forwards",
        "scale-in": "scale-in 0.25s cubic-bezier(0.16,1,0.3,1) forwards",
        shimmer: "shimmer 1.8s infinite linear",
      },
    },
  },
  plugins: [],
};

export default config;
