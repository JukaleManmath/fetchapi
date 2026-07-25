import type {
  AuthScheme,
  Citation,
  GenerationResult,
  IngestionJob,
  Operation,
  PaginatedResponse,
  Schema,
  Source,
  ValidationResult,
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

// ---------------------------------------------------------------------------
// Integration generation
// ---------------------------------------------------------------------------

export function generateIntegration(
  operationId: string,
  language: string,
): Promise<GenerationResult> {
  return request<GenerationResult>("/v1/integrations/generate", {
    method: "POST",
    body: JSON.stringify({ operation_id: operationId, language }),
  });
}

// ---------------------------------------------------------------------------
// Request validation
// ---------------------------------------------------------------------------

export function validateCurl(
  sourceId: string,
  curlCommand: string,
): Promise<ValidationResult> {
  return request<ValidationResult>("/v1/validate/curl", {
    method: "POST",
    body: JSON.stringify({ source_id: sourceId, curl_command: curlCommand }),
  });
}

// ---------------------------------------------------------------------------
// Queries — SSE streaming
// ---------------------------------------------------------------------------

export function streamQuery(
  sourceId: string,
  query: string,
  onToken: (token: string) => void,
  onResult: (citations: Citation[], supportStatus: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/v1/queries/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: sourceId, query }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`${res.status} ${res.statusText}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6).trim();
          if (!json || json === "[DONE]") continue;
          try {
            const event = JSON.parse(json);
            if (event.type === "token") onToken(event.token);
            if (event.type === "result") onResult(event.citations ?? [], event.support_status ?? "");
            if (event.type === "done") onDone();
          } catch {
            // malformed event — skip
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return controller;
}
