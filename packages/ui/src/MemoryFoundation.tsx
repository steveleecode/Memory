import type {
  KeyboardEvent as ReactKeyboardEvent,
  ReactNode,
  RefObject,
  SyntheticEvent,
} from "react";
import {
  Component,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import type { SearchResponseContract, SearchResultContract } from "@memory/types";
import { pressElement, useEntranceMotion } from "./animations";
import { Button } from "./Button";
import { StatusPill } from "./StatusPill";
import type { SpatialPoint } from "./SpatialGraph3D";

type ApprovedRoot = {
  id: string;
  userId: string;
  backendSourceId: string | null;
  displayName: string;
  canonicalRoot: string;
  platform: string;
  scanStatus: string;
  watcherStatus: string;
  lastSuccessfulScan: string | null;
  lastDetectedEvent: string | null;
  lastSynchronizationError: string | null;
  fileCount: number;
  indexedCount: number;
  failedCount: number;
  skippedCount: number;
  pendingChangeCount: number;
};

type FolderSelection = {
  path: string;
  displayName: string;
  platform: string;
};

type ScanProgress = {
  approvedRootId: string;
  status: string;
  discovered: number;
  processed: number;
  indexed: number;
  skipped: number;
  failed: number;
  unsupported: number;
  pending: number;
  lastRelativePath: string | null;
  error: string | null;
};

type DriveConnection = {
  id: string | null;
  status: string;
  account_email: string | null;
  last_successful_synchronization_time: string | null;
  sync_status: string;
  last_synchronization_error: string | null;
  indexed_count: number;
  failed_count: number;
  skipped_count: number;
  unchanged_count: number;
  last_summary: Record<string, unknown> | null;
};

type ViewMode = "space" | "timeline" | "list";
type DialogMode = "auth" | "sources" | "settings" | "ask" | "shortcuts" | null;
type SearchStatus = "idle" | "searching" | "complete" | "empty" | "cancelled" | "error";
type OnboardingStep = "explain" | "connect" | "sync" | "first-search" | "done";
type AskScope = "file" | "cluster" | "results";

type SearchSession = {
  query: string;
  results: SearchResultContract[];
  completedAt: string | null;
};

type AskMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  citations: SearchResultContract[];
  insufficientEvidence?: boolean;
};

const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001";
const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const AUTH_TOKEN_STORAGE_KEY = "memory.authToken";
const AUTH_EMAIL_STORAGE_KEY = "memory.authEmail";
const AUTH_USER_ID_STORAGE_KEY = "memory.authUserId";
const ONBOARDING_STORAGE_KEY = "memory.onboardingComplete";
const HISTORY_STORAGE_KEY = "memory.searchHistory";
const MAX_HISTORY = 8;

const searchStages = ["Retrieving indexed chunks", "Grouping related files", "Preparing views"];
const SpatialGraph3D = lazy(() => import("./SpatialGraph3D"));

export function MemoryFoundation() {
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
  const [userId, setUserId] = useState(
    () => window.localStorage.getItem(AUTH_USER_ID_STORAGE_KEY) ?? DEFAULT_USER_ID,
  );
  const [email, setEmail] = useState(
    () => window.localStorage.getItem(AUTH_EMAIL_STORAGE_KEY) ?? "user@memory.local",
  );
  const [authToken, setAuthToken] = useState(
    () => window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) ?? "",
  );
  const [onboardingStep, setOnboardingStep] = useState<OnboardingStep>(() =>
    window.localStorage.getItem(ONBOARDING_STORAGE_KEY) ? "done" : "explain",
  );
  const [roots, setRoots] = useState<ApprovedRoot[]>([]);
  const [progress, setProgress] = useState<Record<string, ScanProgress>>({});
  const [message, setMessage] = useState("Connect a source to begin building Memory.");
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [session, setSession] = useState<SearchSession>({
    query: "",
    results: [],
    completedAt: null,
  });
  const [searchStatus, setSearchStatus] = useState<SearchStatus>("idle");
  const [searchStageIndex, setSearchStageIndex] = useState(0);
  const [drive, setDrive] = useState<DriveConnection | null>(null);
  const [isDriveBusy, setIsDriveBusy] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("space");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [sourceFilter, setSourceFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortMode, setSortMode] = useState<"relevance" | "modified" | "name">("relevance");
  const [searchHistory, setSearchHistory] = useState<string[]>(() => readHistory(email));
  const [askMessages, setAskMessages] = useState<AskMessage[]>([]);
  const [askInput, setAskInput] = useState("");
  const [askScope, setAskScope] = useState<AskScope>("file");
  const [isAsking, setIsAsking] = useState(false);

  const isDesktop = useMemo(
    () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window,
    [],
  );

  const selectedResult =
    session.results.find((result) => result.document_id === selectedId) ?? null;

  const indexedCount = roots.reduce((total, root) => total + root.indexedCount, 0);
  const hasAnySource = roots.length > 0 || Boolean(drive?.id);
  const readyCount = indexedCount + (drive?.indexed_count ?? 0);

  const sourceOptions = useMemo(() => {
    const options = new Map<string, string>();
    session.results.forEach((result) => {
      options.set(result.source_metadata.display_name, result.source_metadata.display_name);
    });
    return Array.from(options.values());
  }, [session.results]);

  const typeOptions = useMemo(() => {
    const options = new Map<string, string>();
    session.results.forEach((result) => {
      options.set(fileTypeLabel(result), fileTypeLabel(result));
    });
    return Array.from(options.values());
  }, [session.results]);

  const filteredResults = useMemo(() => {
    const next = session.results.filter((result) => {
      const sourceMatches =
        sourceFilter === "all" || result.source_metadata.display_name === sourceFilter;
      const typeMatches = typeFilter === "all" || fileTypeLabel(result) === typeFilter;
      return sourceMatches && typeMatches;
    });
    return next.toSorted((a, b) => {
      if (sortMode === "name") {
        return a.title.localeCompare(b.title);
      }
      if (sortMode === "modified") {
        return dateValue(b) - dateValue(a);
      }
      return b.score - a.score;
    });
  }, [session.results, sortMode, sourceFilter, typeFilter]);

  const refreshRoots = useCallback(async () => {
    const approved = await invoke<ApprovedRoot[]>("list_approved_folders");
    setRoots(approved);
    const entries = await Promise.all(
      approved.map(
        async (root) =>
          [
            root.id,
            await invoke<ScanProgress>("read_scan_progress", { approvedRootId: root.id }),
          ] as const,
      ),
    );
    setProgress(Object.fromEntries(entries));
  }, []);

  const refreshDrive = useCallback(async () => {
    const response = await fetch(
      `${normalizedBackend(backendUrl)}/sources/google-drive/status?user_id=${encodeURIComponent(
        userId,
      )}`,
      { headers: authHeaders(authToken) },
    );
    if (!response.ok) {
      throw new Error(cleanError(await response.text(), "Could not read Google Drive status."));
    }
    setDrive((await response.json()) as DriveConnection);
  }, [authToken, backendUrl, userId]);

  useEffect(() => {
    if (!isDesktop) {
      return;
    }
    void refreshRoots().catch((caught: unknown) => {
      setMessage("Local folder state is temporarily unavailable.");
      setError(cleanError(errorMessage(caught), "Local folder state is temporarily unavailable."));
    });
  }, [isDesktop, refreshRoots]);

  useEffect(() => {
    void refreshDrive().catch(() => {
      setDrive(null);
    });
  }, [refreshDrive]);

  useEffect(() => {
    if (!authToken) {
      return;
    }
    let cancelled = false;
    async function hydrateSession() {
      const response = await fetch(`${normalizedBackend(backendUrl)}/auth/me`, {
        headers: authHeaders(authToken),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as {
        user_id: string;
        email: string;
      };
      if (cancelled) {
        return;
      }
      setUserId(payload.user_id);
      setEmail(payload.email);
      window.localStorage.setItem(AUTH_USER_ID_STORAGE_KEY, payload.user_id);
      window.localStorage.setItem(AUTH_EMAIL_STORAGE_KEY, payload.email);
    }
    void hydrateSession().catch(() => {
      if (cancelled) {
        return;
      }
      setAuthToken("");
      setUserId(DEFAULT_USER_ID);
      window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      window.localStorage.removeItem(AUTH_USER_ID_STORAGE_KEY);
    });
    return () => {
      cancelled = true;
    };
  }, [authToken, backendUrl]);

  useEffect(() => {
    if (searchStatus !== "searching") {
      return;
    }
    const timer = window.setInterval(() => {
      setSearchStageIndex((index) => (index + 1) % searchStages.length);
    }, 900);
    return () => {
      window.clearInterval(timer);
    };
  }, [searchStatus]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (isDesktop) {
        void refreshRoots().catch(() => undefined);
      }
      void refreshDrive().catch(() => undefined);
    }, 15_000);
    return () => {
      window.clearInterval(timer);
    };
  }, [isDesktop, refreshDrive, refreshRoots]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isTyping =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable === true;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        focusSearch();
      }
      if (!isTyping && event.key === "/") {
        event.preventDefault();
        focusSearch();
      }
      if (event.key === "Escape") {
        if (searchStatus === "searching") {
          cancelSearch();
        } else if (dialog) {
          setDialog(null);
        } else if (selectedId) {
          setSelectedId(null);
        }
      }
      if (!isTyping && event.key.toLowerCase() === "g") {
        setViewMode("space");
      }
      if (!isTyping && event.key.toLowerCase() === "t") {
        setViewMode("timeline");
      }
      if (!isTyping && event.key.toLowerCase() === "l") {
        setViewMode("list");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [dialog, searchStatus, selectedId]);

  function focusSearch() {
    searchInputRef.current?.focus();
    searchInputRef.current?.select();
  }

  async function signIn() {
    setError(null);
    try {
      const response = await fetch(`${normalizedBackend(backendUrl)}/auth/sign-in`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as {
        access_token: string;
        user_id: string;
        email: string;
      };
      setAuthToken(payload.access_token);
      setUserId(payload.user_id);
      setEmail(payload.email);
      setSearchHistory(readHistory(payload.email));
      window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, payload.access_token);
      window.localStorage.setItem(AUTH_EMAIL_STORAGE_KEY, payload.email);
      window.localStorage.setItem(AUTH_USER_ID_STORAGE_KEY, payload.user_id);
      setMessage("Signed in. Your sources and history are scoped to this account.");
      if (onboardingStep === "explain") {
        setOnboardingStep("connect");
      }
      setDialog(null);
    } catch (caught) {
      setError(cleanError(errorMessage(caught), "Sign-in failed. Your data was not changed."));
    }
  }

  async function connectDrive() {
    setIsDriveBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${normalizedBackend(backendUrl)}/sources/google-drive/oauth/start`,
        {
          method: "POST",
          headers: { ...authHeaders(authToken), "content-type": "application/json" },
          body: JSON.stringify({ user_id: userId }),
        },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as { authorization_url: string };
      window.location.assign(payload.authorization_url);
    } catch (caught) {
      setError(
        cleanError(
          errorMessage(caught),
          "Google Drive authorization could not start. Your files remain untouched.",
        ),
      );
    } finally {
      setIsDriveBusy(false);
    }
  }

  async function syncDrive(mode: "initial" | "incremental") {
    if (!drive?.id) {
      return;
    }
    setIsDriveBusy(true);
    setError(null);
    setMessage(
      mode === "initial"
        ? "Google Drive synchronization started."
        : "Checking Google Drive for changes.",
    );
    try {
      const response = await fetch(
        `${normalizedBackend(backendUrl)}/sources/google-drive/${drive.id}/sync/${mode}`,
        {
          method: "POST",
          headers: { ...authHeaders(authToken), "content-type": "application/json" },
          body: JSON.stringify({ user_id: userId }),
        },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await refreshDrive();
      setMessage("Google Drive synchronization finished.");
      if (onboardingStep === "sync") {
        setOnboardingStep("first-search");
      }
    } catch (caught) {
      setError(
        cleanError(
          errorMessage(caught),
          "Google Drive synchronization failed. Existing indexed results remain available.",
        ),
      );
    } finally {
      setIsDriveBusy(false);
    }
  }

  async function disconnectDrive() {
    if (
      !drive?.id ||
      !window.confirm(
        "Disconnect Google Drive? Credentials will be removed and Memory will attempt to revoke provider access. Indexed content may remain until removed through source cleanup.",
      )
    ) {
      return;
    }
    setIsDriveBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${normalizedBackend(backendUrl)}/sources/google-drive/${drive.id}/disconnect`,
        {
          method: "POST",
          headers: { ...authHeaders(authToken), "content-type": "application/json" },
          body: JSON.stringify({ user_id: userId }),
        },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await refreshDrive();
      setMessage("Google Drive is disconnected.");
    } catch (caught) {
      setError(cleanError(errorMessage(caught), "Google Drive could not be disconnected."));
    } finally {
      setIsDriveBusy(false);
    }
  }

  async function addFolder() {
    if (!isDesktop) {
      setMessage("Open Memory in the desktop app to grant a local folder.");
      return;
    }
    setError(null);
    try {
      const selection = await invoke<FolderSelection | null>("select_folder");
      if (!selection) {
        return;
      }
      const root = await invoke<ApprovedRoot>("register_approved_folder", {
        request: {
          userId,
          displayName: selection.displayName,
          path: selection.path,
          backendUrl,
          authToken,
        },
      });
      setMessage(`${root.displayName} is approved. Start a scan when you are ready.`);
      await refreshRoots();
      if (onboardingStep === "connect") {
        setOnboardingStep("sync");
      }
    } catch (caught) {
      setError(
        cleanError(
          errorMessage(caught),
          "The local folder could not be approved. Existing sources were not changed.",
        ),
      );
    }
  }

  async function scanNow(root: ApprovedRoot) {
    setError(null);
    setMessage(`Scanning ${root.displayName}. Progress is shown as files are discovered.`);
    try {
      await invoke<ScanProgress>("start_scan", {
        request: {
          approvedRootId: root.id,
          backendUrl,
          authToken,
        },
      });
      await refreshRoots();
      if (onboardingStep === "sync") {
        setOnboardingStep("first-search");
      }
    } catch (caught) {
      setError(
        cleanError(
          errorMessage(caught),
          "Local scan failed. Files remain in their original location and indexed results remain available.",
        ),
      );
    }
  }

  async function toggleWatching(root: ApprovedRoot) {
    setError(null);
    try {
      if (root.watcherStatus === "watching") {
        await invoke("stop_watching_folder", { approvedRootId: root.id });
        setMessage(`Watching paused for ${root.displayName}.`);
      } else {
        await invoke<ApprovedRoot>("start_watching_folder", {
          request: {
            approvedRootId: root.id,
            backendUrl,
            authToken,
          },
        });
        setMessage(`Watching resumed for ${root.displayName}.`);
      }
      await refreshRoots();
    } catch (caught) {
      setError(cleanError(errorMessage(caught), "Watching could not be updated."));
    }
  }

  async function removeFolder(root: ApprovedRoot) {
    const confirmed = window.confirm(
      `Remove ${root.displayName}? This revokes desktop access to the folder.`,
    );
    if (!confirmed) {
      return;
    }
    const deleteIndexedDocuments = window.confirm(
      `Also remove indexed documents for ${root.displayName} from active search results?`,
    );
    setError(null);
    try {
      await invoke("remove_folder", {
        approvedRootId: root.id,
        deleteIndexedDocuments,
        backendUrl,
        authToken,
      });
      setMessage(`${root.displayName} was removed from approved folders.`);
      await refreshRoots();
    } catch (caught) {
      setError(cleanError(errorMessage(caught), "The folder could not be removed."));
    }
  }

  async function search(event?: SyntheticEvent) {
    event?.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || searchStatus === "searching") {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setSearchStatus("searching");
    setSearchStageIndex(0);
    setError(null);
    setMessage("Searching real indexed content.");
    try {
      const response = await fetch(`${normalizedBackend(backendUrl)}/search`, {
        method: "POST",
        headers: { ...authHeaders(authToken), "content-type": "application/json" },
        body: JSON.stringify({ user_id: userId, query: trimmed, limit: 50 }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as SearchResponseContract;
      setSession({
        query: payload.query,
        results: payload.results,
        completedAt: new Date().toISOString(),
      });
      setSelectedId(payload.results[0]?.document_id ?? null);
      setSearchStatus(payload.results.length ? "complete" : "empty");
      setMessage(
        payload.results.length
          ? `${String(payload.results.length)} indexed files matched.`
          : "No indexed files matched. Try broader wording or check source progress.",
      );
      saveHistory(email, trimmed);
      setSearchHistory(readHistory(email));
      if (onboardingStep === "first-search") {
        completeOnboarding();
      }
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setSearchStatus("cancelled");
        setMessage("Search cancelled. Previous results remain available.");
      } else {
        setSearchStatus("error");
        setError(
          cleanError(
            errorMessage(caught),
            "Search is temporarily unavailable. Existing results remain on screen.",
          ),
        );
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    }
  }

  function cancelSearch() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSearchStatus("cancelled");
  }

  async function openResult(result: SearchResultContract, action: "open" | "reveal") {
    setError(null);
    try {
      if (result.source_metadata.kind === "google_drive") {
        const url = driveWebUrl(result);
        if (url) {
          window.open(url, "_blank", "noopener,noreferrer");
          return;
        }
        const response = await fetch(
          `${normalizedBackend(backendUrl)}/sources/google-drive/documents/${result.document_id}/open`,
          { headers: authHeaders(authToken) },
        );
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const payload = (await response.json()) as { drive_web_url: string | null };
        if (payload.drive_web_url) {
          window.open(payload.drive_web_url, "_blank", "noopener,noreferrer");
          return;
        }
        setMessage("This Drive result does not include an openable Google Drive URL.");
        return;
      }
      if (action === "open" && !isDesktop) {
        setMessage("Open the desktop app to open local files.");
        return;
      }
      if (action === "reveal" && !isDesktop) {
        setMessage("Open the desktop app to reveal local files.");
        return;
      }
      const metadata = result.source_metadata.document_metadata;
      const sourceId = stringFrom(metadata.source_id);
      const relativePath = stringFrom(metadata.relative_path);
      const root = roots.find((item) => item.backendSourceId === sourceId);
      if (!root || !relativePath) {
        setMessage("This result does not have an active approved desktop folder.");
        return;
      }
      const command = action === "open" ? "open_file_default_app" : "reveal_file_in_manager";
      await invoke(command, {
        request: {
          approvedRootId: root.id,
          relativePath,
        },
      });
    } catch (caught) {
      setError(
        cleanError(
          errorMessage(caught),
          action === "open"
            ? "The original file could not be opened."
            : "The original file could not be revealed.",
        ),
      );
    }
  }

  function completeOnboarding() {
    window.localStorage.setItem(ONBOARDING_STORAGE_KEY, "true");
    setOnboardingStep("done");
  }

  function clearSearchHistory() {
    window.localStorage.removeItem(historyKey(email));
    setSearchHistory([]);
  }

  function selectRelative(offset: number) {
    if (filteredResults.length === 0) {
      return;
    }
    const currentIndex = Math.max(
      0,
      filteredResults.findIndex((result) => result.document_id === selectedId),
    );
    const nextIndex = Math.min(Math.max(currentIndex + offset, 0), filteredResults.length - 1);
    const next = filteredResults[nextIndex];
    if (next) {
      setSelectedId(next.document_id);
    }
  }

  function onResultsKeyDown(event: ReactKeyboardEvent) {
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      event.preventDefault();
      selectRelative(1);
    }
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      event.preventDefault();
      selectRelative(-1);
    }
    if (event.key === "Enter" && selectedResult) {
      event.preventDefault();
      setSelectedId(selectedResult.document_id);
    }
  }

  function askMemory(event: SyntheticEvent) {
    event.preventDefault();
    const text = askInput.trim();
    if (!text || isAsking) {
      return;
    }
    const citations = askCitations(askScope, selectedResult, filteredResults);
    const userMessage: AskMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text,
      citations: [],
    };
    setAskMessages((messages) => [...messages, userMessage]);
    setAskInput("");
    setIsAsking(true);

    window.setTimeout(() => {
      const insufficientEvidence = citations.length === 0;
      const answer: AskMessage = {
        id: crypto.randomUUID(),
        role: insufficientEvidence ? "system" : "assistant",
        text: insufficientEvidence
          ? "Memory does not have enough indexed evidence in this search session to answer that safely."
          : groundedAnswer(text, citations, askScope),
        citations,
        insufficientEvidence,
      };
      setAskMessages((messages) => [...messages, answer]);
      setIsAsking(false);
    }, 420);
  }

  const experience = !authToken ? "entry" : hasAnySource ? "workspace" : "sources";
  const sourceStatusLabel = hasAnySource
    ? readyCount > 0
      ? `${String(readyCount)} indexed`
      : "Connected"
    : "No sources";
  const quietPrompts = searchHistory.slice(0, 3);

  return (
    <main className="memory-app">
      <Atmosphere />
      <div className="memory-shell">
        <header className="topbar">
          <button className="brand" type="button" onClick={focusSearch} aria-label="Focus search">
            <span className="brand-mark" aria-hidden="true">
              M
            </span>
            <span>Memory</span>
          </button>
          {experience === "entry" ? (
            <button
              className="topbar-link"
              type="button"
              onClick={() => {
                setDialog("auth");
              }}
            >
              Sign in
            </button>
          ) : (
            <nav className="topbar-actions" aria-label="Primary">
              <button
                className="source-indicator"
                type="button"
                onClick={() => {
                  setDialog("sources");
                }}
              >
                <span aria-hidden="true" />
                {sourceStatusLabel}
              </button>
              <button type="button" className="kbd-button" onClick={focusSearch}>
                Cmd/Ctrl K
              </button>
              <button
                className="account-button"
                type="button"
                onClick={() => {
                  setDialog("settings");
                }}
                aria-label="Account settings"
              >
                {emailInitial(email)}
              </button>
            </nav>
          )}
        </header>

        {experience === "entry" ? (
          <EntryExperience
            openAuth={() => {
              setDialog("auth");
            }}
          />
        ) : null}

        {experience === "sources" ? (
          <SourceConnectionExperience
            drive={drive}
            roots={roots}
            progress={progress}
            isDesktop={isDesktop}
            isDriveBusy={isDriveBusy}
            connectDrive={connectDrive}
            addFolder={addFolder}
            syncDrive={() =>
              drive?.id
                ? void syncDrive(
                    drive.last_successful_synchronization_time ? "incremental" : "initial",
                  )
                : undefined
            }
            scanRoots={() => {
              roots.forEach((root) => void scanNow(root));
            }}
            hasAnySource={hasAnySource}
            readyCount={readyCount}
            message={message}
            error={error}
          />
        ) : null}

        {experience === "workspace" ? (
          <WorkspaceExperience
            query={query}
            setQuery={setQuery}
            searchInputRef={searchInputRef}
            searchStatus={searchStatus}
            searchStageIndex={searchStageIndex}
            search={search}
            cancelSearch={cancelSearch}
            message={message}
            error={error}
            session={session}
            filteredResults={filteredResults}
            sourceOptions={sourceOptions}
            typeOptions={typeOptions}
            sourceFilter={sourceFilter}
            typeFilter={typeFilter}
            sortMode={sortMode}
            setSourceFilter={setSourceFilter}
            setTypeFilter={setTypeFilter}
            setSortMode={setSortMode}
            viewMode={viewMode}
            setViewMode={setViewMode}
            selectedId={selectedId}
            hoveredId={hoveredId}
            setSelectedId={setSelectedId}
            setHoveredId={setHoveredId}
            openResult={openResult}
            onResultsKeyDown={onResultsKeyDown}
            quietPrompts={quietPrompts}
            setDialog={setDialog}
            setAskScope={setAskScope}
          />
        ) : null}
      </div>

      {selectedResult ? (
        <FileInspector
          result={selectedResult}
          related={relatedResults(selectedResult, session.results)}
          openResult={openResult}
          selectResult={setSelectedId}
          close={() => {
            setSelectedId(null);
          }}
          ask={() => {
            setAskScope("file");
            setDialog("ask");
          }}
        />
      ) : null}

      {dialog === "sources" ? (
        <SourceDialog
          close={() => {
            setDialog(null);
          }}
          drive={drive}
          roots={roots}
          progress={progress}
          isDesktop={isDesktop}
          isDriveBusy={isDriveBusy}
          connectDrive={connectDrive}
          syncDrive={syncDrive}
          disconnectDrive={disconnectDrive}
          addFolder={addFolder}
          scanNow={scanNow}
          toggleWatching={toggleWatching}
          removeFolder={removeFolder}
        />
      ) : null}
      {dialog === "auth" ? (
        <AuthDialog
          close={() => {
            setDialog(null);
          }}
          email={email}
          setEmail={setEmail}
          signIn={signIn}
          authToken={authToken}
          error={error}
        />
      ) : null}
      {dialog === "settings" ? (
        <SettingsDialog
          close={() => {
            setDialog(null);
          }}
          backendUrl={backendUrl}
          setBackendUrl={setBackendUrl}
          userId={userId}
          setUserId={setUserId}
          email={email}
          setEmail={setEmail}
          signIn={signIn}
          authToken={authToken}
          clearSearchHistory={clearSearchHistory}
        />
      ) : null}
      {dialog === "shortcuts" ? (
        <ShortcutsDialog
          close={() => {
            setDialog(null);
          }}
        />
      ) : null}
      {dialog === "ask" ? (
        <AskDialog
          close={() => {
            setDialog(null);
          }}
          selected={selectedResult}
          resultCount={filteredResults.length}
          scope={askScope}
          setScope={setAskScope}
          messages={askMessages}
          input={askInput}
          setInput={setAskInput}
          isAsking={isAsking}
          ask={askMemory}
          retry={() => {
            const lastUser = askMessages.findLast((item) => item.role === "user");
            if (lastUser) {
              setAskInput(lastUser.text);
            }
          }}
          newThread={() => {
            setAskMessages([]);
          }}
          openResult={openResult}
        />
      ) : null}
    </main>
  );
}

function Atmosphere() {
  return (
    <div className="memory-atmosphere" aria-hidden="true">
      <span className="memory-atmosphere__line memory-atmosphere__line--a" />
      <span className="memory-atmosphere__line memory-atmosphere__line--b" />
      <span className="memory-atmosphere__node memory-atmosphere__node--a" />
      <span className="memory-atmosphere__node memory-atmosphere__node--b" />
      <span className="memory-atmosphere__node memory-atmosphere__node--c" />
      <span className="memory-atmosphere__field" />
    </div>
  );
}

function EntryExperience({ openAuth }: { openAuth: () => void }) {
  return (
    <section className="entry-hero" aria-labelledby="entry-title">
      <div className="hero-object">
        <span className="hero-object__glint" aria-hidden="true" />
        <span className="hero-object__text">Search a project, idea, decision, note, or moment</span>
        <span className="hero-object__key">Enter</span>
      </div>
      <div className="entry-copy">
        <h1 id="entry-title">Find the work you remember, even when you forgot where it lives.</h1>
        <p>Connect the places you choose. Search by idea, project, or moment.</p>
        <div className="hero-actions">
          <Button variant="primary" onClick={openAuth}>
            Get started
          </Button>
          <Button variant="ghost" onClick={openAuth}>
            Sign in
          </Button>
        </div>
      </div>
    </section>
  );
}

function SourceConnectionExperience({
  drive,
  roots,
  progress,
  isDesktop,
  isDriveBusy,
  connectDrive,
  addFolder,
  syncDrive,
  scanRoots,
  hasAnySource,
  readyCount,
  message,
  error,
}: {
  drive: DriveConnection | null;
  roots: ApprovedRoot[];
  progress: Record<string, ScanProgress>;
  isDesktop: boolean;
  isDriveBusy: boolean;
  connectDrive: () => Promise<void>;
  addFolder: () => Promise<void>;
  syncDrive: () => void;
  scanRoots: () => void;
  hasAnySource: boolean;
  readyCount: number;
  message: string;
  error: string | null;
}) {
  return (
    <section className="connect-stage" aria-labelledby="connect-title">
      <div className="connect-panel">
        <div className="connect-copy">
          <p className="eyebrow">Private by selection</p>
          <h1 id="connect-title">Where does your work live?</h1>
          <p>
            Choose only the places Memory may search. Originals stay in Drive or on your machine.
          </p>
        </div>
        <div className="source-choice-grid">
          <button
            className="source-choice source-choice--drive"
            type="button"
            onClick={() => void connectDrive()}
            disabled={isDriveBusy}
          >
            <span className="source-choice__icon">G</span>
            <span>
              <strong>Google Drive</strong>
              <small>Authorize the Drive account you want to search.</small>
            </span>
            <em>{drive?.id ? driveStatusText(drive) : "Connect"}</em>
          </button>
          <button
            className="source-choice source-choice--local"
            type="button"
            onClick={() => void addFolder()}
          >
            <span className="source-choice__icon">L</span>
            <span>
              <strong>Local folder</strong>
              <small>
                {isDesktop ? "Select a folder from this device." : "Available in the desktop app."}
              </small>
            </span>
            <em>{roots.length > 0 ? `${String(roots.length)} connected` : "Choose"}</em>
          </button>
        </div>
        <div className="connect-footer" aria-live="polite">
          <SourceStatusLine drive={drive} roots={roots} progress={progress} pendingCount={0} />
          <div className="source-actions">
            <Button disabled={!hasAnySource} onClick={syncDrive}>
              Sync Drive
            </Button>
            <Button disabled={!hasAnySource} onClick={scanRoots}>
              Scan folders
            </Button>
          </div>
        </div>
        {readyCount > 0 ? (
          <p className="message">{String(readyCount)} indexed files are ready for search.</p>
        ) : (
          <p className="message">{message}</p>
        )}
        {error ? <ErrorState message={error} retry={syncDrive} /> : null}
      </div>
    </section>
  );
}

function WorkspaceExperience({
  query,
  setQuery,
  searchInputRef,
  searchStatus,
  searchStageIndex,
  search,
  cancelSearch,
  message,
  error,
  session,
  filteredResults,
  sourceOptions,
  typeOptions,
  sourceFilter,
  typeFilter,
  sortMode,
  setSourceFilter,
  setTypeFilter,
  setSortMode,
  viewMode,
  setViewMode,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
  openResult,
  onResultsKeyDown,
  quietPrompts,
  setDialog,
  setAskScope,
}: {
  query: string;
  setQuery: (value: string) => void;
  searchInputRef: RefObject<HTMLInputElement | null>;
  searchStatus: SearchStatus;
  searchStageIndex: number;
  search: (event?: SyntheticEvent) => Promise<void>;
  cancelSearch: () => void;
  message: string;
  error: string | null;
  session: SearchSession;
  filteredResults: SearchResultContract[];
  sourceOptions: string[];
  typeOptions: string[];
  sourceFilter: string;
  typeFilter: string;
  sortMode: "relevance" | "modified" | "name";
  setSourceFilter: (value: string) => void;
  setTypeFilter: (value: string) => void;
  setSortMode: (value: "relevance" | "modified" | "name") => void;
  viewMode: ViewMode;
  setViewMode: (value: ViewMode) => void;
  selectedId: string | null;
  hoveredId: string | null;
  setSelectedId: (id: string) => void;
  setHoveredId: (id: string | null) => void;
  openResult: (result: SearchResultContract, action: "open" | "reveal") => Promise<void>;
  onResultsKeyDown: (event: ReactKeyboardEvent) => void;
  quietPrompts: string[];
  setDialog: (dialog: DialogMode) => void;
  setAskScope: (scope: AskScope) => void;
}) {
  const hasSessionResults = session.results.length > 0;
  const hasFilteredResults = filteredResults.length > 0;
  const heroRef = useRef<HTMLElement | null>(null);
  const resultsRef = useRef<HTMLElement | null>(null);
  useEntranceMotion(heroRef, "panel", []);
  useEntranceMotion(resultsRef, "panel", [session.query]);
  return (
    <>
      <section className="workspace-hero" aria-labelledby="search-title" ref={heroRef}>
        <div className="workspace-copy">
          <p className="eyebrow">Memory workspace</p>
          <h1 id="search-title">Search by meaning, not location.</h1>
        </div>
        <form
          className={`search-composer ${searchStatus === "searching" ? "is-searching" : ""}`}
          onSubmit={(event) => void search(event)}
        >
          <label className="visually-hidden" htmlFor="memory-search">
            Search indexed files
          </label>
          <input
            id="memory-search"
            ref={searchInputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            placeholder="Search a project, idea, decision, note, or moment"
            autoComplete="off"
          />
          {searchStatus === "searching" ? (
            <Button onClick={cancelSearch}>Cancel</Button>
          ) : (
            <Button type="submit" variant="primary" disabled={!query.trim()}>
              Search
            </Button>
          )}
        </form>
        <div className="workspace-hints" aria-live="polite">
          <span>{statusText(searchStatus, searchStageIndex)}</span>
          <span>{message}</span>
        </div>
        {quietPrompts.length > 0 && !session.query ? (
          <div className="recent-searches" aria-label="Recent searches">
            {quietPrompts.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  setQuery(item);
                  searchInputRef.current?.focus();
                }}
              >
                {item}
              </button>
            ))}
          </div>
        ) : null}
        {error ? <ErrorState message={error} retry={() => void search()} /> : null}
      </section>

      {session.query || searchStatus !== "idle" ? (
        <section className="results-shell" aria-labelledby="results-title" ref={resultsRef}>
          <div className="results-header">
            <div>
              <h2 id="results-title">
                {session.query ? `Results for "${session.query}"` : "Searching"}
              </h2>
              <p>
                {session.completedAt
                  ? `Completed ${new Date(session.completedAt).toLocaleTimeString()}`
                  : "Memory keeps source and match context with each result."}
              </p>
            </div>
            <div className="results-actions">
              <SegmentedControl value={viewMode} onChange={setViewMode} />
              <Button
                onClick={() => {
                  setAskScope("results");
                  setDialog("ask");
                }}
                disabled={!hasFilteredResults}
              >
                Ask
              </Button>
            </div>
          </div>

          {hasSessionResults ? (
            <ResultFilters
              resultCount={filteredResults.length}
              sourceOptions={sourceOptions}
              typeOptions={typeOptions}
              sourceFilter={sourceFilter}
              typeFilter={typeFilter}
              sortMode={sortMode}
              setSourceFilter={setSourceFilter}
              setTypeFilter={setTypeFilter}
              setSortMode={setSortMode}
              reset={() => {
                setSourceFilter("all");
                setTypeFilter("all");
                setSortMode("relevance");
              }}
            />
          ) : null}

          {searchStatus === "searching" && !hasFilteredResults ? <SearchSkeleton /> : null}
          {searchStatus === "empty" ? (
            <EmptyState
              title="No matches yet"
              body="Try broader wording, or let connected sources finish indexing."
            />
          ) : null}
          {searchStatus === "cancelled" ? (
            <EmptyState title="Search cancelled" body="Previous results are still available." />
          ) : null}
          {hasSessionResults && !hasFilteredResults ? (
            <EmptyState
              title="No results match these filters"
              body="Reset the filters or broaden the source and type selection."
            />
          ) : null}

          {hasFilteredResults ? (
            <div onKeyDown={onResultsKeyDown}>
              {viewMode === "space" ? (
                <SpatialView
                  results={filteredResults}
                  selectedId={selectedId}
                  hoveredId={hoveredId}
                  setSelectedId={setSelectedId}
                  setHoveredId={setHoveredId}
                />
              ) : null}
              {viewMode === "timeline" ? (
                <TimelineView
                  results={filteredResults}
                  selectedId={selectedId}
                  setSelectedId={setSelectedId}
                />
              ) : null}
              {viewMode === "list" ? (
                <ResultList
                  results={filteredResults}
                  selectedId={selectedId}
                  setSelectedId={setSelectedId}
                  openResult={openResult}
                />
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

function AuthDialog({
  close,
  email,
  setEmail,
  signIn,
  authToken,
  error,
}: {
  close: () => void;
  email: string;
  setEmail: (email: string) => void;
  signIn: () => Promise<void>;
  authToken: string;
  error: string | null;
}) {
  return (
    <Dialog title="Sign in to Memory" close={close}>
      <div className="auth-panel">
        <p>
          Use the account you want Memory to keep separate. Sources, searches, and history remain
          scoped to this sign-in.
        </p>
        <label>
          Email
          <input
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
            autoComplete="email"
          />
        </label>
        <Button variant="primary" onClick={() => void signIn()}>
          {authToken ? "Refresh sign-in" : "Continue"}
        </Button>
        {error ? <p className="error-text">{error}</p> : null}
      </div>
    </Dialog>
  );
}

function SegmentedControl({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
}) {
  return (
    <div className="segmented" role="tablist" aria-label="Result view">
      {[
        ["space", "Space"],
        ["timeline", "Timeline"],
        ["list", "List"],
      ].map(([mode, label]) => (
        <button
          aria-selected={value === mode}
          className={value === mode ? "is-active" : ""}
          key={mode}
          onClick={() => {
            onChange(mode as ViewMode);
          }}
          role="tab"
          type="button"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function ResultFilters({
  resultCount,
  sourceOptions,
  typeOptions,
  sourceFilter,
  typeFilter,
  sortMode,
  setSourceFilter,
  setTypeFilter,
  setSortMode,
  reset,
}: {
  resultCount: number;
  sourceOptions: string[];
  typeOptions: string[];
  sourceFilter: string;
  typeFilter: string;
  sortMode: "relevance" | "modified" | "name";
  setSourceFilter: (value: string) => void;
  setTypeFilter: (value: string) => void;
  setSortMode: (value: "relevance" | "modified" | "name") => void;
  reset: () => void;
}) {
  const filterActive = sourceFilter !== "all" || typeFilter !== "all" || sortMode !== "relevance";
  return (
    <div className="filters" aria-label="Result filters">
      <div className="filter-summary">
        <strong>{String(resultCount)} visible</strong>
        <span>Refine this memory space</span>
      </div>
      <label>
        Source
        <select
          value={sourceFilter}
          onChange={(event) => {
            setSourceFilter(event.target.value);
          }}
        >
          <option value="all">All sources</option>
          {sourceOptions.map((source) => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </select>
      </label>
      <label>
        Type
        <select
          value={typeFilter}
          onChange={(event) => {
            setTypeFilter(event.target.value);
          }}
        >
          <option value="all">All types</option>
          {typeOptions.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>
      <label>
        Sort
        <select
          value={sortMode}
          onChange={(event) => {
            setSortMode(event.target.value as "relevance" | "modified" | "name");
          }}
        >
          <option value="relevance">Relevance</option>
          <option value="modified">Modified</option>
          <option value="name">Name</option>
        </select>
      </label>
      <button className="filter-reset" type="button" onClick={reset} disabled={!filterActive}>
        Reset
      </button>
    </div>
  );
}

function SpatialView({
  results,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
}: {
  results: SearchResultContract[];
  selectedId: string | null;
  hoveredId: string | null;
  setSelectedId: (id: string) => void;
  setHoveredId: (id: string | null) => void;
}) {
  const points = useMemo(() => spatialPoints(results), [results]);
  const prefersReducedMotion = useReducedMotion();
  const selectedPoint = points.find((point) => point.result.document_id === selectedId);
  const selectedTitle = selectedPoint?.result.title ?? "No file selected";
  const fallback = (
    <SpatialFallback
      points={points}
      selectedId={selectedId}
      hoveredId={hoveredId}
      setSelectedId={setSelectedId}
      setHoveredId={setHoveredId}
    />
  );
  const renderKey = points.map((point) => point.result.document_id).join(":");
  return (
    <div className="spatial-panel">
      <div className="graph-toolbar">
        <span>{prefersReducedMotion ? "Accessible spatial map" : "Spatial file map"}</span>
        <small>{selectedTitle}</small>
        <button
          type="button"
          onClick={(event) => {
            pressElement(event.currentTarget);
            const first = points[0];
            if (first) {
              setSelectedId(first.result.document_id);
            }
          }}
        >
          Recenter
        </button>
        <button
          type="button"
          onClick={(event) => {
            pressElement(event.currentTarget);
            setHoveredId(null);
          }}
        >
          Reset view
        </button>
      </div>
      {prefersReducedMotion ? (
        fallback
      ) : (
        <SpatialRenderBoundary fallback={fallback} resetKey={renderKey}>
          <Suspense fallback={fallback}>
            <SpatialGraph3D
              points={points}
              selectedId={selectedId}
              hoveredId={hoveredId}
              setSelectedId={setSelectedId}
              setHoveredId={setHoveredId}
            />
          </Suspense>
        </SpatialRenderBoundary>
      )}
      {selectedPoint ? (
        <div className="hover-preview">
          <strong>{selectedPoint.result.title}</strong>
          <span>{sourceLabel(selectedPoint.result)}</span>
        </div>
      ) : null}
      <div className="graph-access-list" aria-label="Accessible result map list">
        {points.slice(0, 12).map((point) => (
          <button
            className={point.result.document_id === selectedId ? "is-selected" : ""}
            key={point.result.document_id}
            type="button"
            onClick={() => {
              setSelectedId(point.result.document_id);
            }}
          >
            {point.result.title}
          </button>
        ))}
      </div>
    </div>
  );
}

export class SpatialRenderBoundary extends Component<
  { children: ReactNode; fallback: ReactNode; resetKey: string },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidUpdate(previousProps: { resetKey: string }) {
    if (this.state.hasError && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function SpatialFallback({
  points,
  selectedId,
  hoveredId,
  setSelectedId,
  setHoveredId,
}: {
  points: SpatialPoint[];
  selectedId: string | null;
  hoveredId: string | null;
  setSelectedId: (id: string) => void;
  setHoveredId: (id: string | null) => void;
}) {
  return (
    <svg className="graph" role="img" aria-label="Spatial relationship map" viewBox="0 0 900 520">
      {points.slice(1).map((point) => (
        <line
          className={selectedId && point.result.document_id !== selectedId ? "is-dimmed" : ""}
          key={`${points[0]?.result.document_id ?? "root"}-${point.result.document_id}`}
          x1={points[0]?.x ?? 450}
          y1={points[0]?.y ?? 260}
          x2={point.x}
          y2={point.y}
        />
      ))}
      {points.map((point) => {
        const isSelected = point.result.document_id === selectedId;
        const isHovered = point.result.document_id === hoveredId;
        return (
          <g
            className={`graph-node ${isSelected ? "is-selected" : ""} ${
              selectedId && !isSelected ? "is-dimmed" : ""
            }`}
            key={point.result.document_id}
            tabIndex={0}
            role="button"
            aria-label={`Select ${point.result.title}`}
            onClick={() => {
              setSelectedId(point.result.document_id);
            }}
            onFocus={() => {
              setHoveredId(point.result.document_id);
            }}
            onBlur={() => {
              setHoveredId(null);
            }}
            onMouseEnter={() => {
              setHoveredId(point.result.document_id);
            }}
            onMouseLeave={() => {
              setHoveredId(null);
            }}
          >
            <circle cx={point.x} cy={point.y} r={point.radius} />
            <text x={point.x} y={point.y + point.radius + 18}>
              {isSelected || isHovered || point.priority < 0.22
                ? truncate(point.result.title, 28)
                : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function TimelineView({
  results,
  selectedId,
  setSelectedId,
}: {
  results: SearchResultContract[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
}) {
  const buckets = useMemo(() => timelineBuckets(results), [results]);
  return (
    <div className="timeline">
      {buckets.map((bucket) => (
        <section className="timeline-bucket" key={bucket.label}>
          <time>{bucket.label}</time>
          <div>
            {bucket.items.map((result) => (
              <button
                className={selectedId === result.document_id ? "is-selected" : ""}
                key={result.document_id}
                type="button"
                onClick={() => {
                  setSelectedId(result.document_id);
                }}
              >
                <strong>{result.title}</strong>
                <span>{sourceLabel(result)}</span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function ResultList({
  results,
  selectedId,
  setSelectedId,
  openResult,
}: {
  results: SearchResultContract[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
  openResult: (result: SearchResultContract, action: "open" | "reveal") => Promise<void>;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  useEntranceMotion(listRef, "list", [results.map((result) => result.document_id).join(":")]);
  return (
    <div className="result-list" role="listbox" aria-label="Search results" ref={listRef}>
      {results.map((result) => (
        <article
          className={`result-row ${selectedId === result.document_id ? "is-selected" : ""}`}
          key={result.document_id}
          data-animate-item
          role="option"
          aria-selected={selectedId === result.document_id}
          tabIndex={0}
          onClick={() => {
            setSelectedId(result.document_id);
          }}
          onFocus={() => {
            setSelectedId(result.document_id);
          }}
        >
          <FileIcon result={result} />
          <div className="result-main">
            <h3>{result.title}</h3>
            <p>{sourceLabel(result)}</p>
            <p>{excerpt(result)}</p>
            <span>{whyMatched(result)}</span>
          </div>
          <div className="result-actions">
            <span>{relevanceLabel(result.score)}</span>
            <Button onClick={() => void openResult(result, "open")}>Open</Button>
            <Button onClick={() => void openResult(result, "reveal")}>Reveal</Button>
          </div>
        </article>
      ))}
    </div>
  );
}

function FileInspector({
  result,
  related,
  openResult,
  selectResult,
  close,
  ask,
}: {
  result: SearchResultContract;
  related: SearchResultContract[];
  openResult: (result: SearchResultContract, action: "open" | "reveal") => Promise<void>;
  selectResult: (id: string) => void;
  close: () => void;
  ask: () => void;
}) {
  const inspectorRef = useRef<HTMLElement | null>(null);
  useEntranceMotion(inspectorRef, "panel", [result.document_id]);
  const metadataRows = technicalMetadata(result);
  return (
    <aside className="inspector" aria-labelledby="inspector-title" ref={inspectorRef}>
      <div className="inspector-header">
        <FileIcon result={result} />
        <div>
          <h2 id="inspector-title">{result.title}</h2>
          <p>{friendlySourceLabel(result)}</p>
        </div>
        <button type="button" onClick={close} aria-label="Close inspector">
          Close
        </button>
      </div>
      <div className="inspector-actions inspector-actions--sticky">
        <Button variant="primary" onClick={() => void openResult(result, "open")}>
          Open original
        </Button>
        <Button onClick={ask}>Ask about this</Button>
        <Button
          onClick={() => {
            selectResult(result.document_id);
          }}
        >
          Reveal in graph
        </Button>
      </div>
      <InspectorSection title="Preview">
        <Preview result={result} />
      </InspectorSection>
      <InspectorSection title="Why this matched">
        <p>{whyMatched(result)}</p>
        <dl className="signal-list">
          <div>
            <dt>Meaning</dt>
            <dd>{signalLabel(result.explanation.semantic_score)}</dd>
          </div>
          <div>
            <dt>Text</dt>
            <dd>{signalLabel(result.explanation.text_score)}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              {stringFrom(result.source_metadata.document_metadata.indexing_status) ?? "ready"}
            </dd>
          </div>
        </dl>
      </InspectorSection>
      <InspectorSection title="Connected files">
        {related.length > 0 ? (
          related.map((item) => (
            <button
              className="related-file"
              key={item.document_id}
              type="button"
              onClick={() => {
                selectResult(item.document_id);
              }}
            >
              <span>{item.title}</span>
              <small>{relevanceLabel(item.score)}</small>
            </button>
          ))
        ) : (
          <p>No directly related files in this result set.</p>
        )}
      </InspectorSection>
      <details className="technical-details">
        <summary>Technical details</summary>
        <dl className="signal-list">
          {metadataRows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </details>
    </aside>
  );
}

function SourceDialog(props: {
  close: () => void;
  drive: DriveConnection | null;
  roots: ApprovedRoot[];
  progress: Record<string, ScanProgress>;
  isDesktop: boolean;
  isDriveBusy: boolean;
  connectDrive: () => Promise<void>;
  syncDrive: (mode: "initial" | "incremental") => Promise<void>;
  disconnectDrive: () => Promise<void>;
  addFolder: () => Promise<void>;
  scanNow: (root: ApprovedRoot) => Promise<void>;
  toggleWatching: (root: ApprovedRoot) => Promise<void>;
  removeFolder: (root: ApprovedRoot) => Promise<void>;
}) {
  const { close, drive, roots, progress } = props;
  return (
    <Dialog title="Sources" close={close}>
      <section className="source-card">
        <div className="source-card__header">
          <div>
            <h3>{drive?.account_email ?? "Google Drive"}</h3>
            <p>{driveStatusText(drive)}</p>
          </div>
          <StatusPill
            label={drive?.status ?? "disconnected"}
            tone={drive?.id ? "positive" : "warning"}
          />
        </div>
        <div className="metrics">
          <Metric label="Indexed" value={drive?.indexed_count ?? 0} />
          <Metric label="Skipped" value={drive?.skipped_count ?? 0} />
          <Metric label="Failed" value={drive?.failed_count ?? 0} />
          <Metric label="Unchanged" value={drive?.unchanged_count ?? 0} />
        </div>
        {drive?.last_synchronization_error ? (
          <p className="error-text">{drive.last_synchronization_error}</p>
        ) : null}
        <div className="source-actions">
          {!drive?.id || drive.status === "not_connected" || drive.status === "disconnected" ? (
            <Button
              variant="primary"
              disabled={props.isDriveBusy}
              onClick={() => void props.connectDrive()}
            >
              Connect Drive
            </Button>
          ) : (
            <>
              <Button
                variant="primary"
                disabled={props.isDriveBusy}
                onClick={() =>
                  void props.syncDrive(
                    drive.last_successful_synchronization_time ? "incremental" : "initial",
                  )
                }
              >
                Sync now
              </Button>
              <Button onClick={() => void props.syncDrive("initial")}>Full sync</Button>
              <Button variant="ghost" onClick={() => void props.disconnectDrive()}>
                Disconnect
              </Button>
            </>
          )}
        </div>
      </section>
      <div className="source-actions">
        <Button variant="primary" onClick={() => void props.addFolder()}>
          Add local folder
        </Button>
      </div>
      {roots.map((root) => {
        const current = progress[root.id];
        return (
          <section className="source-card" key={root.id}>
            <div className="source-card__header">
              <div>
                <h3>{root.displayName}</h3>
                <p>{relativeLocation(root.canonicalRoot)}</p>
              </div>
              <StatusPill
                label={root.watcherStatus}
                tone={root.watcherStatus === "watching" ? "positive" : "warning"}
              />
            </div>
            <div className="metrics">
              <Metric label="Indexed" value={root.indexedCount} />
              <Metric label="Skipped" value={root.skippedCount} />
              <Metric label="Failed" value={root.failedCount} />
              <Metric label="Pending" value={root.pendingChangeCount} />
            </div>
            <ProgressLine root={root} progress={current ?? null} />
            {root.lastSynchronizationError ? (
              <p className="error-text">{root.lastSynchronizationError}</p>
            ) : null}
            <div className="source-actions">
              <Button variant="primary" onClick={() => void props.scanNow(root)}>
                Scan now
              </Button>
              <Button onClick={() => void props.toggleWatching(root)}>
                {root.watcherStatus === "watching" ? "Pause watching" : "Resume watching"}
              </Button>
              <Button onClick={() => void props.scanNow(root)}>Retry failures</Button>
              <Button variant="ghost" onClick={() => void props.removeFolder(root)}>
                Remove
              </Button>
            </div>
          </section>
        );
      })}
    </Dialog>
  );
}

function SettingsDialog({
  close,
  backendUrl,
  setBackendUrl,
  userId,
  setUserId,
  email,
  setEmail,
  signIn,
  authToken,
  clearSearchHistory,
}: {
  close: () => void;
  backendUrl: string;
  setBackendUrl: (value: string) => void;
  userId: string;
  setUserId: (value: string) => void;
  email: string;
  setEmail: (value: string) => void;
  signIn: () => Promise<void>;
  authToken: string;
  clearSearchHistory: () => void;
}) {
  return (
    <Dialog title="Settings and Privacy" close={close}>
      <div className="settings-grid">
        <label>
          Backend
          <input
            value={backendUrl}
            onChange={(event) => {
              setBackendUrl(event.target.value);
            }}
          />
        </label>
        <label>
          User ID
          <input
            value={userId}
            onChange={(event) => {
              setUserId(event.target.value);
            }}
          />
        </label>
        <label>
          Email
          <input
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
          />
        </label>
        <Button variant="primary" onClick={() => void signIn()}>
          {authToken ? "Refresh sign-in" : "Sign in"}
        </Button>
      </div>
      <section className="privacy-copy">
        <h3>What Memory stores</h3>
        <p>
          Selected file metadata, extracted text, chunks, embeddings, indexing status, source
          identifiers, and search history are used for retrieval. Original files remain in their
          source. Removing a connector revokes future access; choose indexed data removal when
          available to remove searchable content.
        </p>
      </section>
      <section className="privacy-copy">
        <h3>Controls</h3>
        <div className="source-actions">
          <Button onClick={clearSearchHistory}>Clear search history</Button>
          <Button variant="ghost" onClick={close}>
            Done
          </Button>
        </div>
      </section>
    </Dialog>
  );
}

function AskDialog({
  close,
  selected,
  resultCount,
  scope,
  setScope,
  messages,
  input,
  setInput,
  isAsking,
  ask,
  retry,
  newThread,
  openResult,
}: {
  close: () => void;
  selected: SearchResultContract | null;
  resultCount: number;
  scope: AskScope;
  setScope: (scope: AskScope) => void;
  messages: AskMessage[];
  input: string;
  setInput: (value: string) => void;
  isAsking: boolean;
  ask: (event: SyntheticEvent) => void;
  retry: () => void;
  newThread: () => void;
  openResult: (result: SearchResultContract, action: "open" | "reveal") => Promise<void>;
}) {
  return (
    <Dialog title="Ask Memory" close={close}>
      <div className="ask-scope">
        <button
          className={scope === "file" ? "is-active" : ""}
          disabled={!selected}
          type="button"
          onClick={() => {
            setScope("file");
          }}
        >
          File
        </button>
        <button
          className={scope === "cluster" ? "is-active" : ""}
          type="button"
          onClick={() => {
            setScope("cluster");
          }}
        >
          Cluster
        </button>
        <button
          className={scope === "results" ? "is-active" : ""}
          type="button"
          onClick={() => {
            setScope("results");
          }}
        >
          Results
        </button>
      </div>
      <p className="message">
        Answers are limited to the current search evidence:{" "}
        {selected?.title ?? `${String(resultCount)} results`}.
      </p>
      <div className="ask-thread" aria-live="polite">
        {messages.length === 0 ? (
          <EmptyState
            title="Ask a grounded question"
            body="Memory will cite the files used or say when evidence is insufficient."
          />
        ) : null}
        {messages.map((message) => (
          <article className={`ask-message ask-message--${message.role}`} key={message.id}>
            <p>{message.text}</p>
            {message.citations.length > 0 ? (
              <div className="citations">
                {message.citations.map((citation) => (
                  <button
                    key={citation.document_id}
                    type="button"
                    onClick={() => void openResult(citation, "open")}
                  >
                    {citation.title}
                  </button>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {isAsking ? <p className="message">Checking indexed evidence...</p> : null}
      </div>
      <form className="ask-form" onSubmit={ask}>
        <input
          value={input}
          onChange={(event) => {
            setInput(event.target.value);
          }}
          placeholder="Ask about the selected evidence"
        />
        <Button type="submit" variant="primary" disabled={!input.trim() || isAsking}>
          Ask
        </Button>
      </form>
      <div className="source-actions">
        <Button onClick={retry}>Retry last</Button>
        <Button onClick={newThread}>New thread</Button>
      </div>
    </Dialog>
  );
}

function ShortcutsDialog({ close }: { close: () => void }) {
  return (
    <Dialog title="Keyboard Shortcuts" close={close}>
      <dl className="shortcut-list">
        <div>
          <dt>Focus search</dt>
          <dd>Command K, Control K, or /</dd>
        </div>
        <div>
          <dt>Cancel search or close panel</dt>
          <dd>Escape</dd>
        </div>
        <div>
          <dt>Move through results</dt>
          <dd>Arrow keys</dd>
        </div>
        <div>
          <dt>Switch views</dt>
          <dd>G for space, T for timeline, L for list</dd>
        </div>
        <div>
          <dt>Open selected file</dt>
          <dd>Use the inspector Open original action</dd>
        </div>
      </dl>
    </Dialog>
  );
}

function Dialog({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={close}>
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
      >
        <div className="dialog-header">
          <h2 id="dialog-title">{title}</h2>
          <button type="button" onClick={close} aria-label={`Close ${title}`}>
            x
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function SourceStatusLine({
  drive,
  roots,
  progress,
  pendingCount,
}: {
  drive: DriveConnection | null;
  roots: ApprovedRoot[];
  progress: Record<string, ScanProgress>;
  pendingCount: number;
}) {
  const active = roots.filter((root) => root.watcherStatus === "watching").length;
  const activeProgress = Object.values(progress).find((item) => item.status !== "idle");
  return (
    <div>
      <strong>{active + (drive?.id ? 1 : 0)} active sources</strong>
      <span>
        {activeProgress
          ? `${activeProgress.status}: ${String(activeProgress.indexed)} indexed, ${String(
              activeProgress.pending,
            )} pending`
          : `${String(pendingCount)} pending changes`}
      </span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProgressLine({ root, progress }: { root: ApprovedRoot; progress: ScanProgress | null }) {
  return (
    <div className="progress-line" aria-live="polite">
      <span>{progress?.status ?? root.scanStatus}</span>
      <span>{progress?.lastRelativePath ?? root.lastDetectedEvent ?? "Ready"}</span>
      <meter
        min={0}
        max={Math.max(progress?.discovered ?? root.fileCount, 1)}
        value={progress?.processed ?? root.indexedCount}
      />
    </div>
  );
}

function InspectorSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="inspector-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Preview({ result }: { result: SearchResultContract }) {
  const text = excerpt(result);
  const type = result.type?.toLowerCase() ?? "";
  const previewUrl =
    stringFrom(result.source_metadata.document_metadata.thumbnail_url) ??
    stringFrom(result.source_metadata.document_metadata.preview_url);
  if (type.includes("image") && previewUrl) {
    return <img className="preview-image" src={previewUrl} alt="" />;
  }
  if (type.includes("image")) {
    return (
      <div className="preview-file preview-file--image">
        <FileIcon result={result} />
        <span>Image preview unavailable</span>
      </div>
    );
  }
  if (type.includes("pdf")) {
    return (
      <div className="preview-file">
        <FileIcon result={result} />
        <span>PDF content has been indexed for search.</span>
      </div>
    );
  }
  if (type.includes("spreadsheet") || type.includes("sheet")) {
    return (
      <div className="preview-file">
        <FileIcon result={result} />
        <span>Spreadsheet content is represented by indexed text excerpts.</span>
      </div>
    );
  }
  if (text) {
    return <pre className="preview-text">{text}</pre>;
  }
  return (
    <p>
      Preview is unavailable for this file type. Metadata and the best matching extracted text will
      appear here when indexed.
    </p>
  );
}

function FileIcon({ result }: { result: SearchResultContract }) {
  return (
    <span
      className={`file-icon file-icon--${sourceKindClass(result.source_metadata.kind)}`}
      aria-hidden="true"
    >
      {fileTypeInitial(result)}
    </span>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <div>
        <strong>{message}</strong>
        <p>User data is safe. Retry is available when the backend or source is reachable again.</p>
      </div>
      <Button onClick={retry}>Retry</Button>
    </div>
  );
}

function SearchSkeleton() {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  );
}

function normalizedBackend(url: string) {
  return url.replace(/\/$/, "");
}

function authHeaders(authToken: string) {
  return authToken ? { authorization: `Bearer ${authToken}` } : {};
}

function errorMessage(errorValue: unknown) {
  return errorValue instanceof Error ? errorValue.message : String(errorValue);
}

function cleanError(raw: string, fallback: string) {
  let readable = raw;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (isRecord(parsed)) {
      const detail = parsed.detail;
      if (typeof detail === "string") {
        readable = detail;
      }
    }
  } catch {
    readable = raw;
  }
  const trimmed = readable
    .replace(/\/Users\/[^"\s]+/g, "[local path]")
    .replace(/\s+/g, " ")
    .trim();
  if (!trimmed || trimmed.includes("Traceback") || trimmed.includes("SQL")) {
    return fallback;
  }
  return trimmed.length > 220 ? `${trimmed.slice(0, 217)}...` : trimmed;
}

function readHistory(email: string) {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(historyKey(email)) ?? "[]");
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function saveHistory(email: string, value: string) {
  const next = [value, ...readHistory(email).filter((item) => item !== value)].slice(
    0,
    MAX_HISTORY,
  );
  window.localStorage.setItem(historyKey(email), JSON.stringify(next));
}

function historyKey(email: string) {
  return `${HISTORY_STORAGE_KEY}.${email}`;
}

function relativeLocation(path: string) {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.slice(-2).join(" / ") || path;
}

function resultModifiedAt(result: SearchResultContract) {
  const metadata = result.source_metadata.document_metadata;
  return (
    stringFrom(metadata.modified_time) ??
    stringFrom(metadata.updated_at) ??
    stringFrom(metadata.created_time) ??
    stringFrom(metadata.indexed_at)
  );
}

function dateValue(result: SearchResultContract) {
  const modified = resultModifiedAt(result);
  return modified ? new Date(modified).getTime() || 0 : 0;
}

function sourceLabel(result: SearchResultContract) {
  const path = stringFrom(result.source_metadata.document_metadata.relative_path);
  const modified = resultModifiedAt(result);
  const pieces = [
    result.source_metadata.kind === "google_drive" ? "Google Drive" : "Local folder",
    result.source_metadata.display_name,
    path ? relativeLocation(path) : null,
    modified ? new Date(modified).toLocaleDateString() : null,
  ].filter(Boolean);
  return pieces.join(" / ");
}

function friendlySourceLabel(result: SearchResultContract) {
  const folder = stringFrom(result.source_metadata.document_metadata.relative_path);
  const modified = resultModifiedAt(result);
  const parts = [
    result.source_metadata.kind === "google_drive" ? "Google Drive" : "Local folder",
    result.source_metadata.display_name,
    folder ? relativeLocation(folder) : null,
    modified ? `Modified ${new Date(modified).toLocaleDateString()}` : null,
  ].filter(Boolean);
  return parts.join(" / ");
}

function technicalMetadata(result: SearchResultContract): [string, string][] {
  const metadata = result.source_metadata.document_metadata;
  const rows: [string, string | null][] = [
    ["Document ID", result.document_id],
    ["MIME type", result.type],
    ["Index status", stringFrom(metadata.indexing_status)],
    ["Relative path", stringFrom(metadata.relative_path)],
    ["Drive URL", driveWebUrl(result)],
    ["Source ID", stringFrom(metadata.source_id)],
    ["Modified", resultModifiedAt(result)],
  ];
  return rows
    .filter((row): row is [string, string] => Boolean(row[1]))
    .map(([label, value]) => [label, value.length > 180 ? `${value.slice(0, 177)}...` : value]);
}

function fileTypeLabel(result: SearchResultContract) {
  if (result.type?.includes("pdf")) return "PDF";
  if (result.type?.includes("markdown")) return "Markdown";
  if (result.type?.includes("image")) return "Image";
  if (result.type?.includes("presentation")) return "Presentation";
  if (result.type?.includes("word")) return "Document";
  const extension = stringFrom(result.source_metadata.document_metadata.extension);
  return extension ? extension.toUpperCase() : "File";
}

function fileTypeInitial(result: SearchResultContract) {
  return fileTypeLabel(result).slice(0, 1).toUpperCase();
}

function sourceKindClass(kind: string) {
  return kind === "google_drive" ? "drive" : "local";
}

function excerpt(result: SearchResultContract) {
  return result.matching_excerpts[0] ?? "No extracted preview is available for this result.";
}

function whyMatched(result: SearchResultContract) {
  const signals = result.explanation.signals;
  const semantic = result.explanation.semantic_score;
  const text = result.explanation.text_score;
  if (semantic >= 0.72 && text > 0) {
    return "Matched by similar meaning and related text in the indexed content.";
  }
  if (semantic >= 0.72) {
    return "Matched because the indexed content is semantically close to your query.";
  }
  if (signals.includes("chunk_text_match")) {
    return "Matched because extracted text contains related terms.";
  }
  return "Matched by indexed source content and ranking signals from the search service.";
}

function signalLabel(value: number) {
  if (value >= 0.72) return "Strong";
  if (value >= 0.48) return "Moderate";
  if (value > 0) return "Light";
  return "Not detected";
}

function relevanceLabel(score: number) {
  if (score >= 0.72) return "High relevance";
  if (score >= 0.48) return "Medium relevance";
  return "Low relevance";
}

function driveWebUrl(result: SearchResultContract) {
  const sourceRecord = result.source_metadata as Record<string, unknown>;
  const drive = sourceRecord.drive;
  if (isRecord(drive)) {
    const url = stringFrom(drive.web_url);
    if (url) return url;
  }
  return stringFrom(result.source_metadata.document_metadata.drive_web_url);
}

function stringFrom(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function spatialPoints(results: SearchResultContract[]): SpatialPoint[] {
  const max = Math.max(results.length, 1);
  return results.slice(0, 50).map((result, index) => {
    const ring = Math.floor(index / 8) + 1;
    const angle = (hash(`${result.document_id}:${String(index)}`) % 360) * (Math.PI / 180);
    const relevancePull = 1 - Math.min(Math.max(result.score, 0), 1);
    const radiusFromCenter = 48 + ring * 54 + relevancePull * 80;
    const x = 450 + Math.cos(angle) * radiusFromCenter;
    const y = 260 + Math.sin(angle) * radiusFromCenter * 0.72;
    return {
      result,
      x,
      y,
      x3: (x - 450) / 92,
      y3: (260 - y) / 92,
      z3: ((hash(`${result.document_id}:z`) % 90) - 45) / 90,
      radius: 9 + Math.max(0, result.score) * 12,
      radius3: 0.12 + Math.max(0, result.score) * 0.12,
      priority: index / max,
    };
  });
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    function onChange(event: MediaQueryListEvent) {
      setReduced(event.matches);
    }
    query.addEventListener("change", onChange);
    return () => {
      query.removeEventListener("change", onChange);
    };
  }, []);
  return reduced;
}

function hash(value: string) {
  let output = 0;
  for (let index = 0; index < value.length; index += 1) {
    output = (output * 31 + value.charCodeAt(index)) >>> 0;
  }
  return output;
}

function timelineBuckets(results: SearchResultContract[]) {
  const buckets = new Map<string, SearchResultContract[]>();
  results.forEach((result) => {
    const value = resultModifiedAt(result);
    const label = value
      ? new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" }).format(
          new Date(value),
        )
      : "Date unknown";
    buckets.set(label, [...(buckets.get(label) ?? []), result]);
  });
  return Array.from(buckets.entries()).map(([label, items]) => ({ label, items }));
}

function relatedResults(result: SearchResultContract, results: SearchResultContract[]) {
  const source = result.source_metadata.display_name;
  return results
    .filter(
      (item) =>
        item.document_id !== result.document_id && item.source_metadata.display_name === source,
    )
    .slice(0, 5);
}

function askCitations(
  scope: AskScope,
  selected: SearchResultContract | null,
  results: SearchResultContract[],
) {
  if (scope === "file") {
    return selected ? [selected] : [];
  }
  if (scope === "cluster") {
    return selected
      ? [selected, ...relatedResults(selected, results)].slice(0, 5)
      : results.slice(0, 5);
  }
  return results.slice(0, 8);
}

function groundedAnswer(question: string, citations: SearchResultContract[], scope: AskScope) {
  const titles = citations.map((item) => item.title).join(", ");
  const evidence = citations
    .map((item) => excerpt(item))
    .filter(Boolean)
    .slice(0, 2)
    .join(" ");
  return `Based on ${scope === "file" ? "the selected file" : "the current search evidence"}, Memory found support in ${titles}. ${truncate(
    evidence,
    260,
  )} Question: ${question}`;
}

function statusText(status: SearchStatus, stageIndex: number) {
  if (status === "searching") return searchStages[stageIndex] ?? searchStages[0];
  if (status === "complete") return "Search complete";
  if (status === "empty") return "No results";
  if (status === "cancelled") return "Cancelled";
  if (status === "error") return "Search needs attention";
  return "Ready";
}

function driveStatusText(drive: DriveConnection | null) {
  if (!drive || drive.status === "not_connected") {
    return "No Google Drive account is connected.";
  }
  if (drive.status === "reauthorization_required") {
    return "Google authorization needs to be renewed.";
  }
  if (drive.sync_status === "running" || drive.status === "syncing") {
    return "Synchronization is running.";
  }
  if (drive.last_successful_synchronization_time) {
    return `Last synchronized ${new Date(drive.last_successful_synchronization_time).toLocaleString()}.`;
  }
  return `Connection status: ${drive.status}.`;
}

function emailInitial(email: string) {
  return (email.trim()[0] ?? "M").toUpperCase();
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 3)}...` : value;
}
