/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class", // toggle via <html class="dark">
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // brand
        heliotrope: "#a880ff",
        affair: "#643f83",
        snuff: "#d6c7e1",
        // instructors "space" theme palette (dark theme source values)
        space: {
          900: "#05030A",
          800: "#1A0F26",
          accent: "#A77DFF",
          hover: "#C0A0FF",
        },
        // LMS Dynamic 1-Line Theme Tokens
        lms: {
          cta: "var(--lms-cta)",
          "cta-hover": "var(--lms-cta-hover)",
          "cta-light": "var(--lms-cta-light)",
          "cta-border": "var(--lms-cta-border)",
          accent: "var(--lms-accent)",
          "accent-hover": "var(--lms-accent-hover)",
          "accent-light": "var(--lms-accent-light)",
          "accent-border": "var(--lms-accent-border)",
          "accent-glow": "var(--lms-accent-glow)",
        },
        // semantic tokens (driven by CSS variables in src/index.css)
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
      },
      fontFamily: {
        sans: ["Inter Variable", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Outfit", "Inter Variable", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};
