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
  | "CHUNKING"
  | "EMBEDDING"
  | "INDEXING"
  | "VERIFYING"
  | "ACTIVE"
  | "SUPERSEDED"
  | "FAILED"
  | "CANCELLED";

export interface Source {
  id: string;
  name: string;
  created_at: string;
  active_revision_id: string | null;
  ingestion_stage: string | null;
  latest_job_id: string | null;
}

export interface JobLog {
  id: string;
  job_id: string;
  created_at: string;
  stage: string | null;
  level: string;
  message: string;
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

// ---------------------------------------------------------------------------
// Queries (Chat / Q&A)
// ---------------------------------------------------------------------------

export interface Citation {
  source_id: string;
  chunk_id: string;
  entity_type: string;
  title: string;
  source_url: string | null;
  source_pointer: string | null;
  method: string | null;
  path: string | null;
  reranker_score: number | null;
  chunk_text: string | null;
}

export interface ChatMessage {
  id: string;           // local uuid, use crypto.randomUUID()
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  evidence_citations?: Citation[];
  support_status?: string;
  loading?: boolean;    // true while streaming, false when done
}

// ---------------------------------------------------------------------------
// Integration generation
// ---------------------------------------------------------------------------

export interface ValidationIssue {
  severity: "error" | "warning" | "info";
  message: string;
  field?: string | null;
}

export interface GenerationResult {
  code: string;
  language: string;
  operation_id: string;
  contract_issues: ValidationIssue[];
  syntax_issues: ValidationIssue[];
}

// ---------------------------------------------------------------------------
// Request validation
// ---------------------------------------------------------------------------

export interface DiagnosticFinding {
  category: string;
  severity: "error" | "warning" | "info";
  message: string;
  field?: string | null;
}

export interface ValidationResult {
  matched_operation: { method: string; path: string } | null;
  findings: DiagnosticFinding[];
  corrected_curl: string | null;
  is_valid: boolean;
}
