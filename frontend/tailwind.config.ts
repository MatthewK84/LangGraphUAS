import type { Config } from "tailwindcss";

// Every utility resolves to a token in src/styles/tokens.css. The theme is
// replaced, not extended, so the default palette, radii above 4px, shadows and
// text sizes above 20px do not exist to be reached for (`npm run lint:ui`).
const token = (name: string): string => `var(--${name})`;
const tint = (name: string, percent: number): string =>
  `color-mix(in srgb, var(--${name}) ${String(percent)}%, transparent)`;

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    // Defaults plus `wide`, where the workspace fits two readout tables.
    screens: {
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1536px",
      wide: "1900px",
    },
    colors: {
      transparent: "transparent",
      current: "currentColor",
      app: token("bg-app"),
      panel: token("bg-panel"),
      raised: token("bg-raised"),
      hover: token("bg-hover"),
      selected: token("bg-selected"),
      line: {
        subtle: token("border-subtle"),
        DEFAULT: token("border"),
        strong: token("border-strong"),
      },
      fg: {
        DEFAULT: token("text-primary"),
        secondary: token("text-secondary"),
        muted: token("text-muted"),
        disabled: token("text-disabled"),
      },
      accent: {
        DEFAULT: token("accent"),
        hover: token("accent-hover"),
        text: token("accent-text"),
      },
      focus: token("focus-ring"),
      ok: { DEFAULT: token("status-ok"), tint: tint("status-ok", 14) },
      caution: {
        DEFAULT: token("status-caution"),
        tint: tint("status-caution", 14),
      },
      critical: {
        DEFAULT: token("status-critical"),
        tint: tint("status-critical", 14),
      },
      stale: { DEFAULT: token("status-stale"), tint: tint("status-stale", 14) },
    },
    spacing: {
      0: "0",
      px: "1px",
      0.5: token("space-0-5"),
      1: token("space-1"),
      2: token("space-2"),
      3: token("space-3"),
      4: token("space-4"),
      6: token("space-6"),
      8: token("space-8"),
      row: token("row-h"),
      "row-dense": token("row-h-dense"),
      "row-relaxed": token("row-h-relaxed"),
      control: token("control-h"),
      topbar: token("topbar-h"),
      header: token("panel-header-h"),
      strip: token("strip-h"),
      form: token("form-w"),
      inspector: token("inspector-w"),
      drawer: token("drawer-h"),
    },
    minWidth: { 0: "0", shell: token("shell-min-w") },
    fontFamily: { sans: token("font-ui"), mono: token("font-mono") },
    fontSize: {
      xs: token("text-xs"),
      sm: token("text-sm"),
      md: token("text-md"),
      lg: token("text-lg"),
      xl: token("text-xl"),
      "2xl": token("text-2xl"),
    },
    lineHeight: {
      none: "1",
      tight: token("leading-tight"),
      normal: token("leading-normal"),
    },
    letterSpacing: { normal: "0", label: token("tracking-label") },
    borderRadius: {
      none: "0",
      sm: token("radius-sm"),
      DEFAULT: token("radius-md"),
      full: "9999px",
    },
    boxShadow: { none: "none", popover: token("shadow-popover") },
    transitionDuration: {
      DEFAULT: token("duration-fast"),
      base: token("duration-base"),
    },
    transitionTimingFunction: { DEFAULT: token("ease-out") },
  },
  plugins: [],
};

export default config;
