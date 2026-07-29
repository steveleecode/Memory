export type SourceKind = "google_drive" | "local_folder";

export type SourceStatus = "pending" | "active" | "paused" | "error" | "revoked";

export type DocumentStatus = "discovered" | "extracting" | "indexed" | "failed" | "deleted";

export type RelationshipKind =
  "semantic_similarity" | "shared_source" | "explicit_reference" | "temporal_neighbor";

export type HealthResponse = {
  status: "ok";
  service: "memory-api";
};

export type ReadinessResponse = {
  status: "ready" | "not_ready";
  checks: {
    database: boolean;
    redis: boolean;
    object_storage: boolean;
  };
};

export type UserContract = {
  id: string;
  email: string;
  displayName: string | null;
  createdAt: string;
};

export type SourceContract = {
  id: string;
  userId: string;
  kind: SourceKind;
  status: SourceStatus;
  displayName: string;
  syncCursor: string | null;
  createdAt: string;
  updatedAt: string;
};

export type DocumentContract = {
  id: string;
  userId: string;
  sourceId: string;
  externalId: string;
  title: string;
  mimeType: string | null;
  status: DocumentStatus;
  contentHash: string | null;
  createdAt: string;
  updatedAt: string;
};

export type DocumentChunkContract = {
  id: string;
  userId: string;
  documentId: string;
  ordinal: number;
  tokenCount: number;
  textPreview: string;
};

export type SearchResultExplanation = {
  semantic_score: number;
  text_score: number;
  weights: {
    semantic: number;
    text: number;
  };
  signals: ("chunk_embedding_cosine_similarity" | "chunk_text_match")[];
};

export type SearchResultContract = {
  document_id: string;
  title: string;
  type: string | null;
  score: number;
  matching_excerpts: string[];
  source_metadata: {
    kind: SourceKind;
    display_name: string;
    metadata: Record<string, unknown>;
    document_metadata: Record<string, unknown>;
  };
  explanation: SearchResultExplanation;
};

export type SearchResponseContract = {
  query: string;
  results: SearchResultContract[];
};
