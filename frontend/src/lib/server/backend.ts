// Server-side backend proxy.
//
// This module runs only inside route handlers. It is the sole place the backend
// API key is read, and the variable is deliberately NOT prefixed NEXT_PUBLIC_,
// so Next.js will not inline it into any client bundle. The browser talks to
// this app's own origin; only this process talks to the backend.

const DEFAULT_BACKEND_URL = "http://localhost:8000";

export const PLAN_TIMEOUT_MS = 45_000;
export const CATALOG_TIMEOUT_MS = 15_000;

export interface BackendRequest {
  readonly path: string;
  readonly method: "GET" | "POST";
  readonly timeoutMs: number;
  readonly requestId: string | null;
  readonly body?: string;
}

function backendBaseUrl(): string {
  const configured: string = process.env.BACKEND_API_URL ?? "";
  return configured.length > 0 ? configured : DEFAULT_BACKEND_URL;
}

function buildHeaders(request: BackendRequest): Record<string, string> {
  const headers: Record<string, string> = {};
  const apiKey: string = process.env.BACKEND_API_KEY ?? "";
  if (apiKey.length > 0) {
    headers["X-API-Key"] = apiKey;
  }
  if (request.method === "POST") {
    headers["Content-Type"] = "application/json";
  }
  if (request.requestId !== null && request.requestId.length > 0) {
    headers["X-Request-ID"] = request.requestId;
  }
  return headers;
}

function jsonResponse(
  payload: Record<string, string>,
  status: number,
): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Mirror the upstream status and body, preserving the correlation header. */
async function mirrorResponse(upstream: Response): Promise<Response> {
  const body: string = await upstream.text();
  const headers = new Headers({ "Content-Type": "application/json" });
  const requestId: string | null = upstream.headers.get("X-Request-ID");
  if (requestId !== null) {
    headers.set("X-Request-ID", requestId);
  }
  return new Response(body, { status: upstream.status, headers });
}

/** Convert a transport failure into a gateway status without leaking internals. */
function gatewayError(error: unknown): Response {
  const timedOut: boolean =
    error instanceof DOMException && error.name === "AbortError";
  const detail: string = timedOut
    ? "Backend request timed out"
    : "Backend unreachable";
  console.error(`Backend proxy failure: ${detail}`, error);
  return jsonResponse({ detail }, timedOut ? 504 : 502);
}

/** Forward one request to the backend, attaching the server-held API key. */
export async function forwardToBackend(
  request: BackendRequest,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, request.timeoutMs);
  try {
    const upstream: Response = await fetch(
      `${backendBaseUrl()}${request.path}`,
      {
        method: request.method,
        headers: buildHeaders(request),
        body: request.body,
        signal: controller.signal,
        cache: "no-store",
      },
    );
    return await mirrorResponse(upstream);
  } catch (error: unknown) {
    return gatewayError(error);
  } finally {
    clearTimeout(timer);
  }
}
