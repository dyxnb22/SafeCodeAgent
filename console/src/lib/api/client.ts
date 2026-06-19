/** Typed Team Server fetch client (v2.3.2). */

import { loadConsoleConfig } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiRequestOptions {
  method?: string;
  tenantId: string;
  accessToken: string;
  query?: Record<string, string | undefined>;
  body?: unknown;
  tenantHeader?: boolean;
  idempotencyKey?: string;
  accept?: string;
}

function buildUrl(path: string, query?: Record<string, string | undefined>): string {
  const config = loadConsoleConfig();
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${config.apiBaseUrl}${normalized}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }
  return url.toString();
}

export async function apiFetchPath<T>(
  path: string,
  options: ApiRequestOptions,
): Promise<T> {
  const headers = new Headers();
  headers.set("Authorization", `Bearer ${options.accessToken}`);
  headers.set("Accept", options.accept ?? "application/json");
  if (options.tenantHeader) {
    headers.set("X-Tenant-Id", options.tenantId);
  }
  if (options.idempotencyKey) {
    headers.set("Idempotency-Key", options.idempotencyKey);
  }
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const query = {
    ...options.query,
    tenant_id: options.tenantHeader ? undefined : options.tenantId,
  };

  const response = await fetch(buildUrl(path, query), {
    method: options.method ?? (options.body === undefined ? "GET" : "POST"),
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    throw new ApiError(`API ${response.status}`, response.status, body);
  }

  if (options.accept === "application/zip") {
    return (await response.blob()) as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

export function createApiClient(session: { tenantId: string; accessToken: string }) {
  const base = {
    tenantId: session.tenantId,
    accessToken: session.accessToken,
  };
  return {
    get<T>(path: string, query?: Record<string, string | undefined>) {
      return apiFetchPath<T>(path, { ...base, query });
    },
    post<T>(
      path: string,
      body: unknown,
      opts?: { idempotencyKey?: string; query?: Record<string, string | undefined> },
    ) {
      return apiFetchPath<T>(path, {
        ...base,
        method: "POST",
        tenantHeader: true,
        body,
        idempotencyKey: opts?.idempotencyKey,
        query: opts?.query,
      });
    },
    download(path: string, query?: Record<string, string | undefined>) {
      return apiFetchPath<Blob>(path, {
        ...base,
        accept: "application/zip",
        query,
      });
    },
  };
}
