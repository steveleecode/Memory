use base64::Engine;
use ignore::WalkBuilder;
use notify::{Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs,
    path::{Component, Path, PathBuf},
    process::Command,
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;
use uuid::Uuid;

const MAX_UPLOAD_BYTES: u64 = 32 * 1024 * 1024;
const BUILT_IN_IGNORES: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "dist",
    "build",
    ".next",
    "coverage",
    ".cache",
    ".pnpm-store",
    ".yarn",
    ".venv",
    "venv",
    "__pycache__",
    ".DS_Store",
    "Thumbs.db",
];

fn with_auth(
    builder: reqwest::blocking::RequestBuilder,
    auth_token: Option<&str>,
) -> reqwest::blocking::RequestBuilder {
    if let Some(token) = auth_token.filter(|value| !value.is_empty()) {
        builder.bearer_auth(token)
    } else {
        builder
    }
}

#[derive(Default)]
struct DesktopState {
    roots: HashMap<Uuid, ApprovedRoot>,
    scans: HashMap<Uuid, ScanProgress>,
    watchers: HashMap<Uuid, RecommendedWatcher>,
    pending: HashMap<Uuid, Vec<QueuedChange>>,
    cancellations: HashSet<Uuid>,
}

type SharedState = Arc<Mutex<DesktopState>>;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ApprovedRoot {
    id: Uuid,
    user_id: Uuid,
    backend_source_id: Option<Uuid>,
    #[serde(default)]
    backend_url: Option<String>,
    display_name: String,
    canonical_root: PathBuf,
    root_fingerprint: String,
    platform: String,
    scan_status: String,
    watcher_status: String,
    last_successful_scan: Option<String>,
    last_detected_event: Option<String>,
    last_synchronization_error: Option<String>,
    file_count: usize,
    indexed_count: usize,
    failed_count: usize,
    skipped_count: usize,
    pending_change_count: usize,
    #[serde(default)]
    pending_changes: Vec<QueuedChange>,
    #[serde(default)]
    known_files: HashMap<String, LocalFileSnapshot>,
    created_at: String,
    updated_at: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct FolderSelection {
    path: PathBuf,
    display_name: String,
    platform: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct RegisterFolderRequest {
    user_id: Uuid,
    display_name: String,
    path: PathBuf,
    backend_url: Option<String>,
    auth_token: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ScanRequest {
    approved_root_id: Uuid,
    backend_url: Option<String>,
    auth_token: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct FileActionRequest {
    approved_root_id: Uuid,
    relative_path: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct PathVerification {
    approved_root_id: Uuid,
    relative_path: String,
    canonical_path: Option<PathBuf>,
    inside_approved_root: bool,
    accessible: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ScanProgress {
    approved_root_id: Uuid,
    status: String,
    discovered: usize,
    processed: usize,
    indexed: usize,
    skipped: usize,
    failed: usize,
    unsupported: usize,
    pending: usize,
    last_relative_path: Option<String>,
    error: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct QueuedChange {
    relative_path: String,
    kind: String,
    detected_at: String,
    #[serde(default)]
    platform_file_id: Option<String>,
    #[serde(default)]
    recursive: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct LocalFileSnapshot {
    relative_path: String,
    content_hash: Option<String>,
    platform_file_id: Option<String>,
    size: u64,
    modified_time: Option<String>,
    supported: bool,
    metadata_only: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendSourceResponse {
    id: Uuid,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct BackendIngestResponse {
    status: String,
    indexing_status: String,
    skipped: bool,
}

#[tauri::command]
fn select_folder(app: AppHandle) -> Result<Option<FolderSelection>, String> {
    let selection = app.dialog().file().blocking_pick_folder();
    selection
        .map(|path| {
            let canonical = canonicalize_existing_dir(&path)?;
            Ok(FolderSelection {
                display_name: canonical
                    .file_name()
                    .and_then(|value| value.to_str())
                    .unwrap_or("Local folder")
                    .to_string(),
                path: canonical,
                platform: std::env::consts::OS.to_string(),
            })
        })
        .transpose()
}

#[tauri::command]
fn register_approved_folder(
    app: AppHandle,
    state: State<'_, SharedState>,
    request: RegisterFolderRequest,
) -> Result<ApprovedRoot, String> {
    let canonical_root = canonicalize_existing_dir(&request.path)?;
    let fingerprint = root_fingerprint(&canonical_root);
    let now = now_iso();
    let backend_url = request.backend_url.clone().filter(|value| !value.is_empty());
    let mut root = ApprovedRoot {
        id: Uuid::new_v4(),
        user_id: request.user_id,
        backend_source_id: None,
        backend_url: backend_url.clone(),
        display_name: request.display_name,
        canonical_root,
        root_fingerprint: fingerprint,
        platform: std::env::consts::OS.to_string(),
        scan_status: "idle".to_string(),
        watcher_status: "stopped".to_string(),
        last_successful_scan: None,
        last_detected_event: None,
        last_synchronization_error: None,
        file_count: 0,
        indexed_count: 0,
        failed_count: 0,
        skipped_count: 0,
        pending_change_count: 0,
        pending_changes: Vec::new(),
        known_files: HashMap::new(),
        created_at: now.clone(),
        updated_at: now,
    };
    if let Some(backend_url) = backend_url.as_deref() {
        match register_backend_source(backend_url, &root, request.auth_token.as_deref()) {
            Ok(source_id) => root.backend_source_id = Some(source_id),
            Err(error) => root.last_synchronization_error = Some(error),
        }
    }
    {
        let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard.roots.insert(root.id, root.clone());
        guard.scans.insert(root.id, initial_progress(root.id));
    }
    persist_roots(&app, &state)?;
    Ok(root)
}

#[tauri::command]
fn list_approved_folders(state: State<'_, SharedState>) -> Result<Vec<ApprovedRoot>, String> {
    let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    Ok(guard.roots.values().cloned().collect())
}

#[tauri::command]
fn remove_folder(
    app: AppHandle,
    state: State<'_, SharedState>,
    approved_root_id: Uuid,
    backend_url: Option<String>,
    auth_token: Option<String>,
    delete_indexed_documents: bool,
) -> Result<(), String> {
    stop_watching_folder(app.clone(), state.clone(), approved_root_id).ok();
    if delete_indexed_documents {
        if let Ok(root) = get_root(&state, approved_root_id) {
            let backend_url = backend_url.as_deref().or(root.backend_url.as_deref());
            for snapshot in root.known_files.values() {
                mark_backend_deleted(
                    &root,
                    &snapshot.relative_path,
                    snapshot.platform_file_id.clone(),
                    backend_url,
                    auth_token.as_deref(),
                    false,
                )
                .ok();
            }
        }
    }
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    guard.roots.remove(&approved_root_id);
    guard.scans.remove(&approved_root_id);
    guard.pending.remove(&approved_root_id);
    drop(guard);
    persist_roots(&app, &state)
}

#[tauri::command]
fn start_scan(
    app: AppHandle,
    state: State<'_, SharedState>,
    request: ScanRequest,
) -> Result<ScanProgress, String> {
    let root = get_root(&state, request.approved_root_id)?;
    remember_backend_url(&app, &state, root.id, request.backend_url.clone())?;
    let root = get_root(&state, request.approved_root_id)?;
    test_root_access(&root)?;
    let backend_url = request.backend_url.as_deref().or(root.backend_url.as_deref());
    ensure_backend_source(&app, &state, root.id, backend_url, request.auth_token.as_deref()).ok();
    let root = get_root(&state, request.approved_root_id)?;
    let mut progress = ScanProgress {
        approved_root_id: root.id,
        status: "scanning_locally".to_string(),
        ..initial_progress(root.id)
    };
    update_progress(&state, progress.clone())?;

    let memoryignore = load_memoryignore(&root.canonical_root);
    let mut seen = HashSet::new();
    clear_cancellation(&state, root.id)?;
    flush_pending_changes(&app, &state, root.id, backend_url, request.auth_token.as_deref())?;
    for entry in WalkBuilder::new(&root.canonical_root)
        .hidden(false)
        .filter_entry(move |entry| should_visit(entry.path(), &memoryignore))
        .build()
    {
        if is_cancelled(&state, root.id)? {
            progress.status = "cancelled".to_string();
            update_progress(&state, progress.clone())?;
            update_root_after_scan(&app, &state, &progress)?;
            return Ok(progress);
        }
        let entry = match entry {
            Ok(value) => value,
            Err(error) => {
                progress.failed += 1;
                progress.error = Some(error.to_string());
                update_progress(&state, progress.clone())?;
                continue;
            }
        };
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        progress.discovered += 1;
        let relative = relative_path(&root, path)?;
        seen.insert(relative.clone());
        progress.last_relative_path = Some(relative.clone());
        if !is_supported_file(path) {
            if let Ok(snapshot) = snapshot_for_path(&root, path, None, false, false) {
                remember_known_file(&app, &state, root.id, snapshot)?;
            }
            progress.unsupported += 1;
            progress.skipped += 1;
            update_progress(&state, progress.clone())?;
            continue;
        }
        match process_file(&root, path, backend_url, request.auth_token.as_deref()) {
            Ok(result) => {
                remember_known_file(&app, &state, root.id, result.snapshot)?;
                match result.outcome {
                    FileProcessOutcome::Indexed => progress.indexed += 1,
                    FileProcessOutcome::Skipped => progress.skipped += 1,
                    FileProcessOutcome::Queued => {
                        queue_change(&app, &state, root.id, relative, "scan_pending", None, false)?;
                        progress.pending += 1;
                    }
                }
            }
            Err(error) => {
                queue_change(&app, &state, root.id, relative, "scan_pending", None, false).ok();
                progress.failed += 1;
                progress.error = Some(error);
            }
        }
        progress.processed += 1;
        update_progress(&state, progress.clone())?;
    }
    reconcile_deleted_files(&app, &state, &root, &seen, backend_url, request.auth_token.as_deref())?;
    clear_cancellation(&state, root.id)?;
    progress.status = "ready".to_string();
    progress.error = None;
    update_progress(&state, progress.clone())?;
    update_root_after_scan(&app, &state, &progress)?;
    Ok(progress)
}

#[tauri::command]
fn cancel_scan(
    state: State<'_, SharedState>,
    approved_root_id: Uuid,
) -> Result<ScanProgress, String> {
    {
        let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard.cancellations.insert(approved_root_id);
    }
    let mut progress = get_progress(&state, approved_root_id)?;
    progress.status = "cancel_requested".to_string();
    update_progress(&state, progress.clone())?;
    Ok(progress)
}

#[tauri::command]
fn read_scan_progress(
    state: State<'_, SharedState>,
    approved_root_id: Uuid,
) -> Result<ScanProgress, String> {
    get_progress(&state, approved_root_id)
}

#[tauri::command]
fn start_watching_folder(
    app: AppHandle,
    state: State<'_, SharedState>,
    request: ScanRequest,
) -> Result<ApprovedRoot, String> {
    remember_backend_url(&app, &state, request.approved_root_id, request.backend_url.clone())?;
    let root = get_root(&state, request.approved_root_id)?;
    test_root_access(&root)?;
    let backend_url = request.backend_url.clone().or(root.backend_url.clone());
    install_watcher(&app, state.inner(), root.id, backend_url, request.auth_token.clone())?;
    get_root(&state, request.approved_root_id)
}

fn install_watcher(
    app: &AppHandle,
    state: &SharedState,
    root_id: Uuid,
    backend_url: Option<String>,
    auth_token: Option<String>,
) -> Result<(), String> {
    let root = {
        let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard
            .roots
            .get(&root_id)
            .cloned()
            .ok_or_else(|| "approved folder not found".to_string())?
    };
    let (tx, rx) = mpsc::channel::<notify::Result<Event>>();
    let mut watcher = notify::recommended_watcher(move |event| {
        tx.send(event).ok();
    })
    .map_err(|error| error.to_string())?;
    watcher
        .watch(&root.canonical_root, RecursiveMode::Recursive)
        .map_err(|error| error.to_string())?;

    {
        let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard.watchers.insert(root.id, watcher);
        if let Some(stored) = guard.roots.get_mut(&root.id) {
            stored.backend_url = backend_url.clone().or(stored.backend_url.clone());
            stored.watcher_status = "watching".to_string();
            stored.updated_at = now_iso();
        }
    }
    persist_roots(app, state)?;

    let thread_state = Arc::clone(state);
    let thread_app = app.clone();
    thread::spawn(move || watcher_loop(thread_app, thread_state, root, rx, backend_url, auth_token));
    Ok(())
}

#[tauri::command]
fn stop_watching_folder(
    app: AppHandle,
    state: State<'_, SharedState>,
    approved_root_id: Uuid,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    guard.watchers.remove(&approved_root_id);
    if let Some(root) = guard.roots.get_mut(&approved_root_id) {
        root.watcher_status = "stopped".to_string();
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(&app, &state)
}

#[tauri::command]
fn reveal_file_in_manager(
    state: State<'_, SharedState>,
    request: FileActionRequest,
) -> Result<(), String> {
    let path = validate_relative_path(&state, request.approved_root_id, &request.relative_path)?;
    reveal_path(&path)
}

#[tauri::command]
fn open_file_default_app(
    state: State<'_, SharedState>,
    request: FileActionRequest,
) -> Result<(), String> {
    let path = validate_relative_path(&state, request.approved_root_id, &request.relative_path)?;
    tauri_plugin_opener::open_path(path.to_string_lossy().to_string(), None::<&str>)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn verify_file_inside_approved_root(
    state: State<'_, SharedState>,
    request: FileActionRequest,
) -> Result<PathVerification, String> {
    let root = get_root(&state, request.approved_root_id)?;
    match validated_child(&root, &request.relative_path) {
        Ok(path) => Ok(PathVerification {
            approved_root_id: root.id,
            relative_path: request.relative_path,
            canonical_path: Some(path.clone()),
            inside_approved_root: true,
            accessible: path.exists(),
        }),
        Err(_) => Ok(PathVerification {
            approved_root_id: root.id,
            relative_path: request.relative_path,
            canonical_path: None,
            inside_approved_root: false,
            accessible: false,
        }),
    }
}

#[tauri::command]
fn test_approved_folder_access(
    state: State<'_, SharedState>,
    approved_root_id: Uuid,
) -> Result<bool, String> {
    let root = get_root(&state, approved_root_id)?;
    Ok(test_root_access(&root).is_ok())
}

enum FileProcessOutcome {
    Indexed,
    Skipped,
    Queued,
}

struct FileProcessResult {
    outcome: FileProcessOutcome,
    snapshot: LocalFileSnapshot,
}

fn process_file(
    root: &ApprovedRoot,
    path: &Path,
    backend_url: Option<&str>,
    auth_token: Option<&str>,
) -> Result<FileProcessResult, String> {
    wait_until_stable(path)?;
    let canonical = canonicalize_existing_file(path)?;
    ensure_inside_root(&root.canonical_root, &canonical)?;
    let metadata = fs::metadata(&canonical).map_err(|error| error.to_string())?;
    let metadata_only = is_metadata_only_file(&canonical);
    let content = if metadata_only {
        metadata_content(root, &canonical, &metadata)?.into_bytes()
    } else {
        fs::read(&canonical).map_err(|error| error.to_string())?
    };
    let hash = hex_sha256(&content);
    let relative = relative_path(root, &canonical)?;
    let snapshot = snapshot_for_path(&root, &canonical, Some(hash.clone()), true, metadata_only)?;
    if backend_url.is_none() || root.backend_source_id.is_none() {
        return Ok(FileProcessResult {
            outcome: FileProcessOutcome::Queued,
            snapshot,
        });
    }
    let body = serde_json::json!({
        "user_id": root.user_id,
        "source_id": root.backend_source_id.expect("checked above"),
        "relative_path": relative,
        "filename": canonical.file_name().and_then(|value| value.to_str()).unwrap_or("file"),
        "mime_type": if metadata_only {
            Some("text/plain")
        } else {
            mime_guess::from_path(&canonical).first_raw()
        },
        "size": metadata.len(),
        "modified_time": system_time_iso(metadata.modified().ok()),
        "created_time": system_time_iso(metadata.created().ok()),
        "parent_directory": Path::new(&relative).parent().and_then(|value| value.to_str()),
        "platform_file_id": platform_file_id(&metadata),
        "content_hash": hash,
        "content_base64": base64::engine::general_purpose::STANDARD.encode(content),
        "metadata_only": metadata_only,
    });
    let url = format!(
        "{}/sources/local-folders/{}/files",
        backend_url.unwrap().trim_end_matches('/'),
        root.backend_source_id.unwrap()
    );
    let response: BackendIngestResponse = with_auth(
        reqwest::blocking::Client::new().post(url),
        auth_token,
    )
    .json(&body)
    .send()
        .map_err(|error| error.to_string())?
        .error_for_status()
        .map_err(|error| error.to_string())?
        .json()
        .map_err(|error| error.to_string())?;
    Ok(FileProcessResult {
        outcome: if response.skipped {
            FileProcessOutcome::Skipped
        } else {
            FileProcessOutcome::Indexed
        },
        snapshot,
    })
}

fn watcher_loop(
    app: AppHandle,
    state: SharedState,
    root: ApprovedRoot,
    rx: mpsc::Receiver<notify::Result<Event>>,
    backend_url: Option<String>,
    auth_token: Option<String>,
) {
    let mut pending: HashMap<PathBuf, (String, SystemTime)> = HashMap::new();
    loop {
        match rx.recv_timeout(Duration::from_millis(800)) {
            Ok(Ok(event)) => {
                let kind = event_kind(&event.kind);
                for path in event.paths {
                    pending.insert(path, (kind.clone(), SystemTime::now()));
                }
            }
            Ok(Err(error)) => {
                set_root_error(&app, &state, root.id, format!("watcher failure: {error}")).ok();
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                let now = SystemTime::now();
                let ready: Vec<(PathBuf, String)> = pending
                    .iter()
                    .filter(|(_, (_, detected))| {
                        now.duration_since(*detected).unwrap_or_default() >= Duration::from_millis(1200)
                    })
                    .map(|(path, (kind, _))| (path.clone(), kind.clone()))
                    .collect();
                for (path, kind) in ready {
                    pending.remove(&path);
                    handle_watcher_path(
                        &app,
                        &state,
                        &root,
                        &path,
                        &kind,
                        backend_url.as_deref(),
                        auth_token.as_deref(),
                    )
                    .ok();
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                set_watcher_status(&app, &state, root.id, "failed").ok();
                break;
            }
        }
    }
}

fn handle_watcher_path(
    app: &AppHandle,
    state: &SharedState,
    root: &ApprovedRoot,
    path: &Path,
    kind: &str,
    backend_url: Option<&str>,
    auth_token: Option<&str>,
) -> Result<(), String> {
    let relative = path.strip_prefix(&root.canonical_root).ok().and_then(|value| value.to_str());
    let Some(relative) = relative else {
        return Ok(());
    };
    let relative = relative.replace('\\', "/");
    if kind == "delete" || !path.exists() {
        let targets = known_delete_targets(state, root.id, &relative)?;
        if targets.is_empty() {
            if mark_backend_deleted(root, &relative, None, backend_url, auth_token, true).is_err() {
                queue_change_raw(state, root.id, relative.clone(), kind.to_string(), None, true)?;
            }
        }
        for target in targets {
            if mark_backend_deleted(
                root,
                &target.relative_path,
                target.platform_file_id.clone(),
                backend_url,
                auth_token,
                false,
            )
            .is_err()
            {
                queue_change_raw(
                    state,
                    root.id,
                    target.relative_path.clone(),
                    kind.to_string(),
                    target.platform_file_id.clone(),
                    false,
                )?;
            } else {
                forget_known_file(app, state, root.id, &target.relative_path)?;
            }
        }
    } else if path.is_file() && is_supported_file(path) {
        match process_file(root, path, backend_url, auth_token) {
            Ok(result) => match result.outcome {
                FileProcessOutcome::Queued => {
                    queue_change_raw(
                        state,
                        root.id,
                        relative.clone(),
                        kind.to_string(),
                        result.snapshot.platform_file_id.clone(),
                        false,
                    )?;
                }
                FileProcessOutcome::Indexed | FileProcessOutcome::Skipped => {
                    remember_known_file_raw(app, state, root.id, result.snapshot)?;
                }
            },
            Err(_) => {
                queue_change_raw(state, root.id, relative.clone(), kind.to_string(), None, false)?;
            }
        }
    }
    {
        let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        if let Some(stored) = guard.roots.get_mut(&root.id) {
            stored.last_detected_event = Some(format!("{kind}: {relative}"));
            stored.updated_at = now_iso();
        }
    }
    persist_roots(app, state)
}

fn register_backend_source(
    backend_url: &str,
    root: &ApprovedRoot,
    auth_token: Option<&str>,
) -> Result<Uuid, String> {
    let body = serde_json::json!({
        "user_id": root.user_id,
        "display_name": root.display_name,
        "root_fingerprint": root.root_fingerprint,
        "platform": root.platform,
        "status": "active",
        "scan_status": "idle",
        "watcher_status": "stopped",
    });
    let url = format!("{}/sources/local-folders", backend_url.trim_end_matches('/'));
    let response: BackendSourceResponse = with_auth(
        reqwest::blocking::Client::new().post(url),
        auth_token,
    )
    .json(&body)
    .send()
        .map_err(|error| error.to_string())?
        .error_for_status()
        .map_err(|error| error.to_string())?
        .json()
        .map_err(|error| error.to_string())?;
    Ok(response.id)
}

fn ensure_backend_source(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    root_id: Uuid,
    backend_url: Option<&str>,
    auth_token: Option<&str>,
) -> Result<(), String> {
    let Some(backend_url) = backend_url else {
        return Ok(());
    };
    let root = get_root(state, root_id)?;
    if root.backend_source_id.is_some() {
        return Ok(());
    }
    let source_id = register_backend_source(backend_url, &root, auth_token)?;
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    if let Some(stored) = guard.roots.get_mut(&root_id) {
        stored.backend_source_id = Some(source_id);
        stored.last_synchronization_error = None;
        stored.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn mark_backend_deleted(
    root: &ApprovedRoot,
    relative: &str,
    platform_file_id: Option<String>,
    backend_url: Option<&str>,
    auth_token: Option<&str>,
    recursive: bool,
) -> Result<(), String> {
    let Some(backend_url) = backend_url else { return Ok(()); };
    let Some(source_id) = root.backend_source_id else { return Ok(()); };
    let body = serde_json::json!({
        "user_id": root.user_id,
        "source_id": source_id,
        "relative_path": relative,
        "platform_file_id": platform_file_id,
        "recursive": recursive,
    });
    let url = format!("{}/sources/local-folders/{source_id}/delete", backend_url.trim_end_matches('/'));
    with_auth(reqwest::blocking::Client::new().post(url), auth_token)
        .json(&body)
        .send()
        .map_err(|error| error.to_string())?
        .error_for_status()
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn reconcile_deleted_files(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    root: &ApprovedRoot,
    seen: &HashSet<String>,
    backend_url: Option<&str>,
    auth_token: Option<&str>,
) -> Result<(), String> {
    let known_files = {
        let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard
            .roots
            .get(&root.id)
            .map(|stored| stored.known_files.clone())
            .unwrap_or_default()
    };
    for snapshot in known_files.values() {
        if !seen.contains(&snapshot.relative_path) {
            mark_backend_deleted(
                root,
                &snapshot.relative_path,
                snapshot.platform_file_id.clone(),
                backend_url,
                auth_token,
                false,
            )
            .ok();
            forget_known_file(app, state.inner(), root.id, &snapshot.relative_path)?;
        }
    }
    Ok(())
}

fn canonicalize_existing_dir(path: &Path) -> Result<PathBuf, String> {
    let canonical = fs::canonicalize(path).map_err(|error| error.to_string())?;
    if !canonical.is_dir() {
        return Err("selected path is not a directory".to_string());
    }
    Ok(canonical)
}

fn canonicalize_existing_file(path: &Path) -> Result<PathBuf, String> {
    let canonical = fs::canonicalize(path).map_err(|error| error.to_string())?;
    if !canonical.is_file() {
        return Err("selected path is not a file".to_string());
    }
    Ok(canonical)
}

fn validated_child(root: &ApprovedRoot, relative: &str) -> Result<PathBuf, String> {
    let requested = Path::new(relative);
    if requested.is_absolute() || requested.components().any(|part| matches!(part, Component::ParentDir)) {
        return Err("path traversal is not allowed".to_string());
    }
    let joined = root.canonical_root.join(requested);
    let canonical = fs::canonicalize(&joined).map_err(|error| error.to_string())?;
    ensure_inside_root(&root.canonical_root, &canonical)?;
    Ok(canonical)
}

fn ensure_inside_root(root: &Path, child: &Path) -> Result<(), String> {
    if child.starts_with(root) {
        Ok(())
    } else {
        Err("path is outside the approved root".to_string())
    }
}

fn relative_path(root: &ApprovedRoot, path: &Path) -> Result<String, String> {
    let canonical = fs::canonicalize(path).map_err(|error| error.to_string())?;
    ensure_inside_root(&root.canonical_root, &canonical)?;
    canonical
        .strip_prefix(&root.canonical_root)
        .map_err(|error| error.to_string())?
        .to_str()
        .map(|value| value.replace('\\', "/"))
        .ok_or_else(|| "path is not valid UTF-8".to_string())
}

fn is_supported_file(path: &Path) -> bool {
    is_indexable_file(path) || is_metadata_only_file(path)
}

fn is_indexable_file(path: &Path) -> bool {
    matches!(
        extension(path).as_deref(),
        Some(
            "txt"
                | "text"
                | "csv"
                | "tsv"
                | "log"
                | "md"
                | "markdown"
                | "mdx"
                | "pdf"
                | "docx"
                | "pptx"
                | "c"
                | "cpp"
                | "cs"
                | "css"
                | "go"
                | "html"
                | "java"
                | "js"
                | "jsx"
                | "json"
                | "kt"
                | "mjs"
                | "py"
                | "rb"
                | "rs"
                | "sh"
                | "sql"
                | "swift"
                | "toml"
                | "ts"
                | "tsx"
                | "yaml"
                | "yml"
        )
    )
}

fn is_metadata_only_file(path: &Path) -> bool {
    matches!(
        extension(path).as_deref(),
        Some(
            "png"
                | "jpg"
                | "jpeg"
                | "gif"
                | "webp"
                | "heic"
                | "svg"
                | "obj"
                | "stl"
                | "gltf"
                | "glb"
                | "fbx"
                | "dae"
                | "step"
                | "stp"
                | "iges"
                | "igs"
                | "dwg"
                | "dxf"
        )
    )
}

fn extension(path: &Path) -> Option<String> {
    path.extension()
        .and_then(|value| value.to_str())
        .map(|value| value.to_ascii_lowercase())
}

fn should_visit(path: &Path, memoryignore: &[String]) -> bool {
    let name = path.file_name().and_then(|value| value.to_str()).unwrap_or("");
    if BUILT_IN_IGNORES.iter().any(|ignored| name == *ignored) {
        return false;
    }
    !memoryignore.iter().any(|pattern| name == pattern || path.to_string_lossy().contains(pattern))
}

fn load_memoryignore(root: &Path) -> Vec<String> {
    fs::read_to_string(root.join(".memoryignore"))
        .unwrap_or_default()
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(ToOwned::to_owned)
        .collect()
}

fn wait_until_stable(path: &Path) -> Result<(), String> {
    let mut previous = file_stability_marker(path)?;
    for _ in 0..5 {
        thread::sleep(Duration::from_millis(250));
        let current = file_stability_marker(path)?;
        if current == previous {
            let size = current.0;
            if size > MAX_UPLOAD_BYTES {
                return Err(format!("file exceeds {} byte upload limit", MAX_UPLOAD_BYTES));
            }
            return Ok(());
        }
        previous = current;
    }
    let size = fs::metadata(path).map_err(|error| error.to_string())?.len();
    if size > MAX_UPLOAD_BYTES {
        return Err(format!("file exceeds {} byte upload limit", MAX_UPLOAD_BYTES));
    }
    Ok(())
}

fn file_stability_marker(path: &Path) -> Result<(u64, Option<SystemTime>), String> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    Ok((metadata.len(), metadata.modified().ok()))
}

fn snapshot_for_path(
    root: &ApprovedRoot,
    path: &Path,
    content_hash: Option<String>,
    supported: bool,
    metadata_only: bool,
) -> Result<LocalFileSnapshot, String> {
    let canonical = fs::canonicalize(path).map_err(|error| error.to_string())?;
    ensure_inside_root(&root.canonical_root, &canonical)?;
    let metadata = fs::metadata(&canonical).map_err(|error| error.to_string())?;
    Ok(LocalFileSnapshot {
        relative_path: relative_path(root, &canonical)?,
        content_hash,
        platform_file_id: platform_file_id(&metadata),
        size: metadata.len(),
        modified_time: system_time_iso(metadata.modified().ok()),
        supported,
        metadata_only,
    })
}

fn metadata_content(
    root: &ApprovedRoot,
    path: &Path,
    metadata: &fs::Metadata,
) -> Result<String, String> {
    let relative = relative_path(root, path)?;
    let filename = path.file_name().and_then(|value| value.to_str()).unwrap_or("file");
    Ok(format!(
        "Filename: {filename}\nRelative path: {relative}\nFile type: {}\nSize: {}\nModified time: {}\nContent indexing: metadata only",
        mime_guess::from_path(path).first_raw().unwrap_or("application/octet-stream"),
        metadata.len(),
        system_time_iso(metadata.modified().ok()).unwrap_or_else(|| "unknown".to_string())
    ))
}

fn get_root(state: &State<'_, SharedState>, id: Uuid) -> Result<ApprovedRoot, String> {
    let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    guard.roots.get(&id).cloned().ok_or_else(|| "approved folder not found".to_string())
}

fn get_progress(state: &State<'_, SharedState>, id: Uuid) -> Result<ScanProgress, String> {
    let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    Ok(guard.scans.get(&id).cloned().unwrap_or_else(|| initial_progress(id)))
}

fn update_progress(state: &State<'_, SharedState>, progress: ScanProgress) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    guard.scans.insert(progress.approved_root_id, progress);
    Ok(())
}

fn initial_progress(id: Uuid) -> ScanProgress {
    ScanProgress {
        approved_root_id: id,
        status: "idle".to_string(),
        discovered: 0,
        processed: 0,
        indexed: 0,
        skipped: 0,
        failed: 0,
        unsupported: 0,
        pending: 0,
        last_relative_path: None,
        error: None,
    }
}

fn queue_change(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    root_id: Uuid,
    relative_path: String,
    kind: &str,
    platform_file_id: Option<String>,
    recursive: bool,
) -> Result<(), String> {
    queue_change_raw(
        state.inner(),
        root_id,
        relative_path,
        kind.to_string(),
        platform_file_id,
        recursive,
    )?;
    persist_roots(app, state)
}

fn queue_change_raw(
    state: &SharedState,
    root_id: Uuid,
    relative_path: String,
    kind: String,
    platform_file_id: Option<String>,
    recursive: bool,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    let queue = guard.pending.entry(root_id).or_default();
    queue.retain(|change| change.relative_path != relative_path);
    queue.push(QueuedChange {
        relative_path,
        kind,
        detected_at: now_iso(),
        platform_file_id,
        recursive,
    });
    let pending_count = queue.len();
    let queue_snapshot = queue.clone();
    if let Some(root) = guard.roots.get_mut(&root_id) {
        root.pending_change_count = pending_count;
        root.pending_changes = queue_snapshot;
    }
    Ok(())
}

fn remove_queued_change(
    app: &AppHandle,
    state: &SharedState,
    root_id: Uuid,
    relative_path: &str,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    let queue_snapshot = if let Some(queue) = guard.pending.get_mut(&root_id) {
        queue.retain(|change| change.relative_path != relative_path);
        queue.clone()
    } else {
        Vec::new()
    };
    if let Some(root) = guard.roots.get_mut(&root_id) {
        root.pending_change_count = queue_snapshot.len();
        root.pending_changes = queue_snapshot;
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn remember_known_file(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    root_id: Uuid,
    snapshot: LocalFileSnapshot,
) -> Result<(), String> {
    remember_known_file_raw(app, state.inner(), root_id, snapshot)
}

fn remember_known_file_raw(
    app: &AppHandle,
    state: &SharedState,
    root_id: Uuid,
    snapshot: LocalFileSnapshot,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    if let Some(root) = guard.roots.get_mut(&root_id) {
        if let Some(platform_file_id) = snapshot.platform_file_id.as_deref() {
            root.known_files
                .retain(|_, existing| existing.platform_file_id.as_deref() != Some(platform_file_id));
        }
        root.known_files
            .retain(|relative_path, _| relative_path != &snapshot.relative_path);
        root.known_files
            .insert(snapshot.relative_path.clone(), snapshot);
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn forget_known_file(
    app: &AppHandle,
    state: &SharedState,
    root_id: Uuid,
    relative_path: &str,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    if let Some(root) = guard.roots.get_mut(&root_id) {
        root.known_files.remove(relative_path);
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn remember_backend_url(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    root_id: Uuid,
    backend_url: Option<String>,
) -> Result<(), String> {
    let Some(backend_url) = backend_url.filter(|value| !value.is_empty()) else {
        return Ok(());
    };
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    if let Some(root) = guard.roots.get_mut(&root_id) {
        root.backend_url = Some(backend_url);
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn is_cancelled(state: &State<'_, SharedState>, root_id: Uuid) -> Result<bool, String> {
    let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    Ok(guard.cancellations.contains(&root_id))
}

fn clear_cancellation(state: &State<'_, SharedState>, root_id: Uuid) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    guard.cancellations.remove(&root_id);
    Ok(())
}

fn flush_pending_changes(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    root_id: Uuid,
    backend_url: Option<&str>,
    auth_token: Option<&str>,
) -> Result<(), String> {
    let root = get_root(state, root_id)?;
    let backend_url = backend_url.or(root.backend_url.as_deref());
    let pending = {
        let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard.pending.get(&root_id).cloned().unwrap_or_default()
    };
    for change in pending {
        if change.kind == "delete" || change.recursive {
            if mark_backend_deleted(
                &root,
                &change.relative_path,
                change.platform_file_id.clone(),
                backend_url,
                auth_token,
                change.recursive,
            )
            .is_ok()
            {
                remove_queued_change(app, state.inner(), root_id, &change.relative_path)?;
                forget_known_file(app, state.inner(), root_id, &change.relative_path)?;
            }
            continue;
        }
        let Ok(path) = validated_child(&root, &change.relative_path) else {
            remove_queued_change(app, state.inner(), root_id, &change.relative_path)?;
            continue;
        };
        if !path.exists() {
            queue_change(
                app,
                state,
                root_id,
                change.relative_path.clone(),
                "delete",
                change.platform_file_id.clone(),
                false,
            )?;
            continue;
        }
        if let Ok(result) = process_file(&root, &path, backend_url, auth_token) {
            match result.outcome {
                FileProcessOutcome::Indexed | FileProcessOutcome::Skipped => {
                    remember_known_file(app, state, root_id, result.snapshot)?;
                    remove_queued_change(app, state.inner(), root_id, &change.relative_path)?;
                }
                FileProcessOutcome::Queued => {}
            }
        }
    }
    Ok(())
}

fn known_delete_targets(
    state: &SharedState,
    root_id: Uuid,
    relative_path: &str,
) -> Result<Vec<LocalFileSnapshot>, String> {
    let prefix = format!("{}/", relative_path.trim_end_matches('/'));
    let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    let Some(root) = guard.roots.get(&root_id) else {
        return Ok(Vec::new());
    };
    Ok(root
        .known_files
        .values()
        .filter(|snapshot| {
            snapshot.relative_path == relative_path || snapshot.relative_path.starts_with(&prefix)
        })
        .cloned()
        .collect())
}

fn update_root_after_scan(
    app: &AppHandle,
    state: &State<'_, SharedState>,
    progress: &ScanProgress,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    let pending_count = guard
        .pending
        .get(&progress.approved_root_id)
        .map(Vec::len)
        .unwrap_or(0);
    if let Some(root) = guard.roots.get_mut(&progress.approved_root_id) {
        root.scan_status = progress.status.clone();
        root.file_count = progress.discovered;
        root.indexed_count = progress.indexed;
        root.failed_count = progress.failed;
        root.skipped_count = progress.skipped + progress.unsupported;
        root.pending_change_count = pending_count;
        if progress.status == "ready" {
            root.last_successful_scan = Some(now_iso());
        }
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn set_watcher_status(
    app: &AppHandle,
    state: &SharedState,
    root_id: Uuid,
    status: &str,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    if let Some(root) = guard.roots.get_mut(&root_id) {
        root.watcher_status = status.to_string();
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn set_root_error(
    app: &AppHandle,
    state: &SharedState,
    root_id: Uuid,
    error: String,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
    if let Some(root) = guard.roots.get_mut(&root_id) {
        root.last_synchronization_error = Some(error);
        root.watcher_status = "failed".to_string();
        root.updated_at = now_iso();
    }
    drop(guard);
    persist_roots(app, state)
}

fn test_root_access(root: &ApprovedRoot) -> Result<(), String> {
    if root.canonical_root.is_dir() {
        fs::read_dir(&root.canonical_root).map_err(|error| error.to_string())?;
        Ok(())
    } else {
        Err("approved folder no longer exists or is not accessible".to_string())
    }
}

fn persist_roots(app: &AppHandle, state: &SharedState) -> Result<(), String> {
    let dir = app.path().app_data_dir().map_err(|error| error.to_string())?;
    fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    let roots: Vec<ApprovedRoot> = {
        let guard = state.lock().map_err(|_| "desktop state lock poisoned".to_string())?;
        guard.roots.values().cloned().collect()
    };
    fs::write(
        dir.join("local_sources.json"),
        serde_json::to_vec_pretty(&roots).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

fn load_roots(app: &AppHandle) -> Vec<ApprovedRoot> {
    let Ok(dir) = app.path().app_data_dir() else {
        return Vec::new();
    };
    let Ok(bytes) = fs::read(dir.join("local_sources.json")) else {
        return Vec::new();
    };
    serde_json::from_slice(&bytes).unwrap_or_default()
}

fn validate_relative_path(
    state: &State<'_, SharedState>,
    root_id: Uuid,
    relative_path: &str,
) -> Result<PathBuf, String> {
    let root = get_root(state, root_id)?;
    validated_child(&root, relative_path)
}

fn root_fingerprint(path: &Path) -> String {
    hex_sha256(path.to_string_lossy().as_bytes())
}

fn hex_sha256(content: impl AsRef<[u8]>) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content);
    format!("{:x}", hasher.finalize())
}

fn now_iso() -> String {
    system_time_iso(Some(SystemTime::now())).unwrap_or_else(|| "unknown".to_string())
}

fn system_time_iso(value: Option<SystemTime>) -> Option<String> {
    value.and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .and_then(|duration| time::OffsetDateTime::from_unix_timestamp(duration.as_secs() as i64).ok())
        .and_then(|datetime| datetime.format(&time::format_description::well_known::Rfc3339).ok())
}

#[cfg(unix)]
fn platform_file_id(metadata: &fs::Metadata) -> Option<String> {
    use std::os::unix::fs::MetadataExt;
    Some(format!("{}:{}", metadata.dev(), metadata.ino()))
}

#[cfg(not(unix))]
fn platform_file_id(_metadata: &fs::Metadata) -> Option<String> {
    None
}

fn event_kind(kind: &EventKind) -> String {
    match kind {
        EventKind::Create(_) => "create",
        EventKind::Modify(_) => "modify",
        EventKind::Remove(_) => "delete",
        _ => "change",
    }
    .to_string()
}

fn reveal_path(path: &Path) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg("-R")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?;
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg("/select,")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?;
        return Ok(());
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let target = path.parent().unwrap_or(path);
        Command::new("xdg-open")
            .arg(target)
            .status()
            .map_err(|error| error.to_string())?;
        return Ok(());
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let mut state = DesktopState::default();
            for mut root in load_roots(&app.handle()) {
                let pending_changes = root.pending_changes.clone();
                state.scans.insert(root.id, initial_progress(root.id));
                state.pending.insert(root.id, pending_changes);
                state.roots.insert(root.id, root);
            }
            let shared_state = Arc::new(Mutex::new(state));
            let restart_watchers: Vec<(Uuid, Option<String>)> = shared_state
                .lock()
                .ok()
                .map(|guard| {
                    guard
                    .roots
                    .values()
                    .filter(|root| root.watcher_status == "watching")
                    .map(|root| (root.id, root.backend_url.clone()))
                    .collect()
                })
                .unwrap_or_default();
            app.manage(Arc::clone(&shared_state));
            for (root_id, backend_url) in restart_watchers {
                install_watcher(&app.handle(), &shared_state, root_id, backend_url, None).ok();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            select_folder,
            register_approved_folder,
            list_approved_folders,
            remove_folder,
            start_scan,
            cancel_scan,
            read_scan_progress,
            start_watching_folder,
            stop_watching_folder,
            reveal_file_in_manager,
            open_file_default_app,
            verify_file_inside_approved_root,
            test_approved_folder_access,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Memory desktop shell");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_relative_traversal() {
        let root = ApprovedRoot {
            id: Uuid::new_v4(),
            user_id: Uuid::new_v4(),
            backend_source_id: None,
            backend_url: None,
            display_name: "Fixture".to_string(),
            canonical_root: std::env::temp_dir(),
            root_fingerprint: "fixture".to_string(),
            platform: "test".to_string(),
            scan_status: "idle".to_string(),
            watcher_status: "stopped".to_string(),
            last_successful_scan: None,
            last_detected_event: None,
            last_synchronization_error: None,
            file_count: 0,
            indexed_count: 0,
            failed_count: 0,
            skipped_count: 0,
            pending_change_count: 0,
            pending_changes: Vec::new(),
            known_files: HashMap::new(),
            created_at: now_iso(),
            updated_at: now_iso(),
        };
        assert!(validated_child(&root, "../outside.txt").is_err());
        assert!(validated_child(&root, "/tmp/outside.txt").is_err());
    }

    #[test]
    fn detects_supported_files() {
        assert!(is_supported_file(Path::new("notes.md")));
        assert!(is_supported_file(Path::new("main.tsx")));
        assert!(!is_supported_file(Path::new("archive.zip")));
    }

    #[test]
    fn built_in_ignores_skip_dependencies() {
        assert!(!should_visit(Path::new("/tmp/node_modules"), &[]));
        assert!(!should_visit(Path::new("/tmp/.git"), &[]));
        assert!(should_visit(Path::new("/tmp/notes"), &[]));
    }
}
