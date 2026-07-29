# Design System

## Tone

Memory should feel composed, quiet, and precise. It should communicate capability through careful interaction design, not decorative density.

## Tokens

Tokens live in `packages/ui/src/tokens.ts` and are mirrored as CSS custom properties in
`packages/ui/src/styles.css`.

- Canvas: warm off-white.
- Raised canvas: near-white for graph and preview surfaces.
- Surface: white.
- Muted surface: quiet gray-beige for segmented controls and separators.
- Text: near-black.
- Accent: restrained teal with stronger and soft variants.
- Source colors: Drive teal-blue and local green.
- State colors: success, warning, and danger with soft backgrounds.
- Focus: teal ring with sufficient contrast.
- Radius: 4px, 6px, and 8px.
- Motion: 140 ms micro-interactions, 220 ms panels, 520 ms graph transitions.
- Graph: node radius and edge-strength tokens are exported for visual tuning.

## Components

The shared app shell now includes:

- `Button`
- `StatusPill`
- search composer
- segmented result view control
- filters
- source cards and progress lines
- result rows
- Three.js spatial graph with SVG/list fallback
- timeline buckets
- file icons
- inspector sections
- preview states
- dialogs
- error and empty states
- Ask Memory citations

## Interaction

- Prefer icon buttons for compact tools where meaning is standard.
- Use visible labels for critical commands.
- Preserve keyboard focus.
- Avoid text overflow in fixed controls.
- Keep graph controls stable in size.
- Keep the graph informational: position means centrality, size means relevance, and source color
  remains secondary.
- Respect `prefers-reduced-motion` and keep the list view as a complete alternative to the graph.
- Do not expose absolute local paths in normal result or inspector copy.
