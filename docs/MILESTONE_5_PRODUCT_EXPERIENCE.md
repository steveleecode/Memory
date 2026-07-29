# Milestone 5 Product Experience

## Scope Delivered

- Authenticated product entry using the existing sign-in endpoint and stored bearer token.
- Progressive onboarding for consent, source connection, synchronization, and first search.
- Unified source management for Google Drive and desktop-approved local folders.
- Search-first home using the real `POST /search` contract.
- Result exploration through space, timeline, and list views with preserved selection.
- React Three Fiber / Three.js spatial graph with deterministic positions and fallback access.
- File inspector with source provenance, preview text, match explanation, related files, and actions.
- Ask Memory session UI scoped to selected file, cluster, or result set with visible citations.
- Settings and privacy dialog for backend/account controls and search history removal.
- Error states that avoid raw stack traces, SQL details, OAuth responses, and absolute local paths.

## API Boundaries

The UI uses existing backend and desktop contracts. It does not redesign search, source, or local
folder APIs. The graph derives stable presentation coordinates from document/search identifiers
because the current search response does not yet include server coordinates or relationship edges.
The frontend does not calculate semantic similarity.

Ask Memory is implemented as a grounded session interface over current search evidence. It cites the
files used and refuses insufficient-evidence requests. A future backend answer endpoint can replace
the local evidence synthesis without changing dialog state or citation rendering.

## Accessibility And Keyboard

- Search focus: Command-K, Control-K, and `/` when not typing.
- Cancel or close: Escape.
- View switching: G, T, and L.
- Result traversal: arrow keys within the result area.
- The spatial graph has an SVG/reduced-motion fallback and an accessible result list.
- Dialogs use modal semantics and labelled headings.
- Live regions announce search, source progress, and Ask Memory status.

## Performance Notes

- Search requests use `AbortController` for cancellation and duplicate prevention.
- Results are filtered and sorted with memoized derived state.
- Graph rendering is capped to 50 nodes and keeps long-result exploration available in list view.
- Expensive preview rendering is avoided; excerpts are shown as safe text.
- Reduced-motion users bypass the WebGL canvas.

## Manual QA Checklist

- Sign in with a development account and verify returning entry opens the product shell.
- Connect Google Drive, run initial sync, search real indexed content, inspect a Drive result, and
  open it in Drive.
- Add a local folder in the desktop app, scan, search, inspect, open, and reveal a local result.
- Switch space to timeline to list and confirm the selected file remains selected.
- Test no-result, cancelled search, backend unavailable, Drive auth loss, and local folder missing
  messages.
- Toggle reduced motion and confirm the SVG/list spatial fallback remains usable.
- Navigate primary search, result selection, inspector close, and dialogs with keyboard only.
