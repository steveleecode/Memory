# Memory Motion System

Memory uses GSAP through `packages/ui/src/animations.ts` for reusable, restrained motion.

## Principles

- Motion should clarify hierarchy, selection, and spatial continuity.
- Keep durations short enough that frequent search and source-management work still feels fast.
- Prefer opacity and transform animations. Avoid layout-changing animation targets.
- Always respect `prefers-reduced-motion`.

## Utilities

- `useEntranceMotion(ref, "panel", keys)` animates shell panels, dialogs, and inspectors.
- `useEntranceMotion(ref, "list", keys)` staggers children marked with `data-animate-item`.
- `pressElement(element)` adds a short tactile press response for compact controls. The shared
  `Button` component uses this automatically while preserving caller pointer handlers.
- `prefersReducedMotion()` is shared by React UI and the 3D graph camera easing.

## Adding Motion

Reuse the shared helpers before adding component-local GSAP code. If a new animation pattern is
needed, add it to `animations.ts` with a descriptive name and document the intended use here.
