# Experience Spec

## Experience Tenets

- Calm, not chatty.
- Spatial, not decorative.
- Trustworthy before magical.
- Inspectable results over opaque summaries.

## Interface Direction

Memory should feel closer to a refined first-party AI workspace than a generic analytics dashboard. Avoid decorative metric cards, oversized marketing panels inside the app, and playful placeholder workflows.

## Implemented Milestone 5 Flows

1. Connect Google Drive through OAuth.
2. Select local folders through Tauri with native file permissions.
3. Watch source sync status.
4. Search in natural language.
5. Open a result with source provenance and match explanation.
6. Move between spatial, timeline, and list views without losing selection.
7. Inspect a file without leaving the search session.
8. Open Drive originals or open/reveal approved local files through the desktop app.
9. Ask grounded questions against selected search evidence with visible citations.

## Product Shell

The normal authenticated view is search-first. Source management, settings, shortcuts, and Ask Memory
are contextual dialogs rather than a permanent dashboard sidebar. The search composer remains the
primary focus and can be focused with Command-K, Control-K, or `/` when the user is not typing in a
field.

The first-run flow is progressive:

- Explain selected-source consent, extraction, cloud indexing, and removal.
- Offer only real available connectors: Google Drive and desktop local folders.
- Show honest stage and count-based synchronization state.
- Let the user enter the product while indexing continues.

## Empty And Loading States

- Empty states should state what is unavailable and why.
- Loading states should be specific: connecting, syncing, extracting, embedding, ranking.
- Development mocks must be visibly labeled.
- Errors state what failed, whether existing indexed data remains available, and the next action.

## Spatial Graph Principles

- Coordinates are stable across sessions.
- Relationship types are visually distinct without becoming noisy.
- Users can return to the same area of the graph.
- Search can focus the graph without re-laying out the entire space.
- The React Three Fiber graph receives typed result data and callbacks from the product shell.
- Reduced-motion and unavailable-WebGL users get the same results through SVG and list fallbacks.

## Current Contract Boundaries

The frontend consumes the existing `SearchResponseContract`, including document id, title, MIME
type, score, excerpts, source metadata, and explanation signals. It derives view coordinates,
timeline buckets, and related-result groups from returned metadata but does not calculate semantic
similarity. A future backend search-experience contract can replace those derived presentation
fields without changing the product shell ownership model.
