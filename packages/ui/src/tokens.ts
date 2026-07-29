export const tokens = {
  color: {
    canvas: "#f6f4ee",
    canvasRaised: "#fbfaf7",
    surface: "#ffffff",
    surfaceMuted: "#ece9df",
    text: "#24231f",
    textMuted: "#68655e",
    border: "#d7d1c4",
    borderStrong: "#bfb8aa",
    accent: "#1f6f68",
    accentStrong: "#164f4a",
    accentSoft: "#dcefeb",
    drive: "#286f7a",
    local: "#4f7660",
    success: "#276b4f",
    successSoft: "#dfeee6",
    warning: "#a96721",
    warningSoft: "#f4e1c8",
    danger: "#9a3021",
    dangerSoft: "#f5ded7",
  },
  typography: {
    family:
      "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    size: {
      caption: "12px",
      body: "15px",
      bodyLarge: "17px",
      heading: "22px",
      displayMin: "42px",
      displayMax: "76px",
    },
    lineHeight: {
      tight: "0.96",
      body: "1.5",
    },
  },
  spacing: {
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    5: "20px",
    6: "24px",
    8: "32px",
  },
  radius: {
    xs: "4px",
    sm: "6px",
    md: "8px",
  },
  border: {
    default: "1px solid #d7d1c4",
    strong: "1px solid #bfb8aa",
  },
  shadow: {
    subtle: "0 1px 2px rgb(36 35 31 / 0.08)",
    panel: "0 18px 46px rgb(36 35 31 / 0.14)",
  },
  motion: {
    fast: "140ms",
    panel: "220ms",
    graph: "520ms",
    easing: "cubic-bezier(0.2, 0, 0, 1)",
  },
  focus: {
    ring: "0 0 0 3px rgb(31 111 104 / 0.18)",
  },
  graph: {
    nodeMin: 0.12,
    nodeMax: 0.24,
    edgeStrength: 1.2,
  },
  breakpoint: {
    tablet: "720px",
    laptop: "980px",
    desktop: "1180px",
  },
} as const;

export type MemoryTokens = typeof tokens;
