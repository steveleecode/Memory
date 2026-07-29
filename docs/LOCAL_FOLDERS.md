# Local Folder Integration

## Desktop Architecture

Local folders are handled only by the Tauri desktop shell. The frontend can ask for narrow commands,
but it cannot read arbitrary paths. Rust owns native folder selection, path canonicalization,
approved-root validation, scanning, watching, opening, and revealing files.

Approved folders are stored in the application data directory as `local_sources.json`. The stored
record includes the approved canonical root, backend source ID, backend URL, scan/watch state,
durable pending changes, and a minimal snapshot of known files. File contents are not stored in this
queue.

## Tauri Permissions

The desktop capability in `apps/desktop/src-tauri/capabilities/default.json` grants core, dialog, and
opener plugin defaults. Filesystem access is intentionally not exposed through a broad plugin scope.
Every filesystem operation goes through a typed command in `src/lib.rs` and validates the approved
root before touching a child path.

## Path Safety

- Folder selection uses the native dialog and stores the canonical selected directory.
- Child file actions reject absolute paths and `..` traversal.
- Existing child paths are canonicalized before open, reveal, or upload.
- Symlinks that resolve outside the approved root are rejected.
- Search results carry relative paths, not absolute local paths.

## Scanning

`start_scan` recursively walks the approved root with built-in ignores plus `.memoryignore`.
Supported files are hashed, uploaded to the backend, and ingested through the existing extraction,
chunking, embedding, and indexing pipeline. If the backend is unavailable, changes are stored in the
durable pending queue and retried at the beginning of a later scan.

The scanner keeps a known-file snapshot. Missing files from the snapshot are tombstoned on the
backend so stale chunks are removed from active search.

## Ignore Rules

Precedence is:

1. Built-in ignores for generated or dependency directories such as `.git`, `node_modules`, `target`,
   `dist`, `build`, `.next`, `coverage`, package-manager caches, virtual environments, and OS
   metadata.
2. Source-level ignore settings when they are added in a future settings UI.
3. `.memoryignore` entries in the approved root.
4. Explicit include paths when they are added in a future settings UI.

The initial `.memoryignore` support is name/substring based rather than full gitignore syntax.

## Watcher Behavior

The desktop watcher uses `notify` recursively, debounces bursts for the same path, waits for writes
to stabilize before reading, and uses content hashes as the final source of truth. Create/modify
events upload the changed file. Delete events tombstone the exact file or all known files under a
deleted folder prefix. Watcher failures mark the source as failed, and a later scan reconciles missed
changes.

Folders that were watching are restarted on app launch using the persisted backend URL and source ID.

## Identity

Local document identity prefers `platform_file_id` when available and falls back to relative path:

- Rename: same platform file ID updates relative-path metadata without creating a new document.
- Move within source: same platform file ID updates folder metadata without re-embedding unchanged
  content.
- Copy: different platform file ID creates a distinct document.
- Delete and recreate: new platform file ID creates a new identity; the old document is tombstoned.
- Replacement with different content: same identity reprocesses because the content hash changes.
- Source removal and re-add: root fingerprint reconnects to the same backend source when the
  canonical root is identical.

## Offline Queue

The desktop app stores only relative path, event kind, platform file ID, recursive flag, and timestamp
for pending changes. It does not store file contents. Queued changes are deduplicated by relative
path, persisted in `local_sources.json`, retried at scan startup, and preserved across restarts.

## Supported Formats

Content indexing uses the backend ingestion pipeline for text, Markdown, PDF, DOCX, PPTX, CSV, and
common source-code files. Image, 3D, and common CAD-like assets are recorded as metadata-only text so
they can be opened from search without claiming binary contents were extracted.

## Platform Limitations

- macOS reveal uses `open -R`.
- Windows reveal uses Explorer selection.
- Linux reveal opens the parent folder with `xdg-open`.
- Platform file IDs are available on Unix through device and inode metadata. Non-Unix platforms fall
  back to relative path until a native stable ID provider is added.
- Very large files are limited by `MEMORY_LOCAL_MAX_UPLOAD_BYTES`; streaming upload remains a future
  improvement.

## Manual Verification

1. Launch the desktop application.
2. Select a real local folder.
3. Confirm the privacy explanation before scanning.
4. Scan one PDF, one Markdown or text file, one source-code file, and one DOCX or PPTX.
5. Search for a semantic concept rather than an exact filename.
6. Open one result and reveal one result.
7. Edit one indexed file and confirm only that file reprocesses.
8. Rename or move the file and confirm metadata updates without re-embedding unchanged content.
9. Delete the file and confirm it disappears from search.
10. Disconnect the network, change another file, reconnect, scan, and confirm the queued change syncs.
11. Restart the app and confirm folders that were watching resume watching.
