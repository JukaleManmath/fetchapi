// ---------------------------------------------------------------------------
// Mirrors the backend domain model - keep in sync with ARCHITECTURE.md §6
// ---------------------------------------------------------------------------

export type RevisionStatus =
  | "QUEUED"
  | "FETCHING"
  | "SNAPSHOTTING"
  | "PARSING"
  | "VALIDATING"
  | "NORMALIZING"
  | "ACTIVE"
  | "SUPERSEDED"
  | "FAILED";

export interface Source {
  id: string;
  name: string;
  created_at: string;
  active_revision_id: string | null;
}

export interface SourceRevision {
  id: string;
  source_id: string;
  status: RevisionStatus;
  spec_url: string | null;
  content_hash: string | null;
  created_at: string;
  activated_at: string | null;
  error_message: string | null;
}

export interface IngestionJob {
  id: string;
  source_id: string;
  revision_id: string;
  stage: RevisionStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Operation {
  id: string;
  revision_id: string;
  operation_id: string;
  method: string;
  path: string;
  summary: string | null;
  description: string | null;
  tags: string[];
  deprecated: boolean;
}

export interface Schema {
  id: string;
  revision_id: string;
  name: string;
  description: string | null;
  schema_type: string | null;
}

export interface AuthScheme {
  id: string;
  revision_id: string;
  name: string;
  scheme_type: string;
  description: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
