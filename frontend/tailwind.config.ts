import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        "card-foreground": "hsl(var(--card-foreground))",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        ring: "hsl(var(--ring))"
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem"
      },
      boxShadow: {
        soft: "0 24px 60px rgba(26, 43, 36, 0.08)"
      },
      backgroundImage: {
        mesh:
          "radial-gradient(circle at top left, rgba(127, 212, 173, 0.28), transparent 28%), radial-gradient(circle at 80% 20%, rgba(255, 210, 146, 0.25), transparent 24%), linear-gradient(180deg, rgba(255,255,255,0.92), rgba(252,249,241,0.92))"
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
};

export default config;
