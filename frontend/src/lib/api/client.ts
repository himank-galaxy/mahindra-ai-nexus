// API client foundation for the FastAPI backend.
//
// The frontend is API-only: every hook fetches from the backend. Queries
// stay client-side only (never during SSR) so the Nitro server needs no
// backend access.

export const apiBaseUrl: string =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

/** True during server rendering (TanStack Start SSR) — never fetch there. */
export const isSsr: boolean = typeof window === "undefined";

/** Queries/mutations only run in the browser. */
export const apiEnabled: boolean = !isSsr;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, message: string, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type ApiInit = Omit<RequestInit, "body"> & { body?: unknown };

/** JSON fetch against `/api/v1`; throws `ApiError` with the backend envelope. */
export async function apiFetch<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { body, headers, ...rest } = init;
  const res = await fetch(`${apiBaseUrl}${path}`, {
    ...rest,
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    let code = "http_error";
    try {
      const payload = (await res.json()) as { detail?: string; code?: string };
      if (payload.detail) detail = payload.detail;
      if (payload.code) code = payload.code;
    } catch {
      // Non-JSON error body — keep the HTTP status text.
    }
    throw new ApiError(res.status, detail, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
