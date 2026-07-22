import type {
  AuthScheme,
  IngestionJob,
  Operation,
  PaginatedResponse,
  Schema,
  Source,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

export function listSources(): Promise<Source[]> {
  return request<Source[]>("/v1/sources");
}

export function getSource(id: string): Promise<Source> {
  return request<Source>(`/v1/sources/${id}`);
}

// ---------------------------------------------------------------------------
// Ingestion
// ---------------------------------------------------------------------------

export function ingestFromUrl(name: string, url: string): Promise<IngestionJob> {
  return request<IngestionJob>("/v1/sources/openapi/url", {
    method: "POST",
    body: JSON.stringify({ name, url }),
  });
}

export async function ingestFromFile(
  name: string,
  file: File
): Promise<IngestionJob> {
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  const res = await fetch(`${BASE}/v1/sources/openapi/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<IngestionJob>;
}

export function getJob(jobId: string): Promise<IngestionJob> {
  return request<IngestionJob>(`/v1/jobs/${jobId}`);
}

// ---------------------------------------------------------------------------
// Canonical entities
// ---------------------------------------------------------------------------

export function listOperations(
  sourceId: string
): Promise<PaginatedResponse<Operation>> {
  return request<PaginatedResponse<Operation>>(
    `/v1/sources/${sourceId}/operations`
  );
}

export function getOperation(operationId: string): Promise<Operation> {
  return request<Operation>(`/v1/operations/${operationId}`);
}

export function listSchemas(
  sourceId: string
): Promise<PaginatedResponse<Schema>> {
  return request<PaginatedResponse<Schema>>(`/v1/sources/${sourceId}/schemas`);
}

export function listAuth(sourceId: string): Promise<AuthScheme[]> {
  return request<AuthScheme[]>(`/v1/sources/${sourceId}/auth`);
}
