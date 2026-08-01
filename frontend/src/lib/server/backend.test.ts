import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CATALOG_TIMEOUT_MS, forwardToBackend } from "./backend";

interface CapturedCall {
  readonly url: string;
  readonly headers: Record<string, string>;
  readonly method: string | undefined;
}

function captureFetch(response: Response): { calls: CapturedCall[] } {
  const calls: CapturedCall[] = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({
      url,
      headers: (init.headers ?? {}) as Record<string, string>,
      method: init.method,
    });
    return Promise.resolve(response);
  });
  return { calls };
}

function jsonUpstream(
  body: string,
  status: number,
  requestId?: string,
): Response {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (requestId !== undefined) {
    headers.set("X-Request-ID", requestId);
  }
  return new Response(body, { status, headers });
}

const CATALOG_REQUEST = {
  path: "/api/aircraft",
  method: "GET",
  timeoutMs: CATALOG_TIMEOUT_MS,
  requestId: null,
} as const;

describe("forwardToBackend", () => {
  beforeEach(() => {
    process.env.BACKEND_API_URL = "http://backend.test:8000";
    delete process.env.BACKEND_API_KEY;
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete process.env.BACKEND_API_URL;
    delete process.env.BACKEND_API_KEY;
  });

  it("attaches the server-held API key so the browser never needs one", async () => {
    process.env.BACKEND_API_KEY = "secret-value";
    const { calls } = captureFetch(jsonUpstream("[]", 200));

    await forwardToBackend(CATALOG_REQUEST);

    expect(calls).toHaveLength(1);
    expect(calls[0]?.headers["X-API-Key"]).toBe("secret-value");
    expect(calls[0]?.url).toBe("http://backend.test:8000/api/aircraft");
  });

  it("omits the API key header when no key is configured", async () => {
    const { calls } = captureFetch(jsonUpstream("[]", 200));

    await forwardToBackend(CATALOG_REQUEST);

    expect(calls[0]?.headers).not.toHaveProperty("X-API-Key");
  });

  it("mirrors the upstream status rather than masking failures", async () => {
    captureFetch(
      jsonUpstream(JSON.stringify({ detail: "Invalid API key" }), 401),
    );

    const result = await forwardToBackend(CATALOG_REQUEST);

    expect(result.status).toBe(401);
    expect(await result.text()).toContain("Invalid API key");
  });

  it("propagates the correlation id in both directions", async () => {
    const { calls } = captureFetch(jsonUpstream("[]", 200, "upstream-id"));

    const result = await forwardToBackend({
      ...CATALOG_REQUEST,
      requestId: "client-id",
    });

    expect(calls[0]?.headers["X-Request-ID"]).toBe("client-id");
    expect(result.headers.get("X-Request-ID")).toBe("upstream-id");
  });

  it("sends a JSON content type only for POST bodies", async () => {
    const { calls } = captureFetch(jsonUpstream("{}", 200));

    await forwardToBackend({
      path: "/api/plan",
      method: "POST",
      timeoutMs: CATALOG_TIMEOUT_MS,
      requestId: null,
      body: "{}",
    });

    expect(calls[0]?.headers["Content-Type"]).toBe("application/json");
    expect(calls[0]?.method).toBe("POST");
  });

  it("returns 502 without leaking internals when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.reject(new TypeError("ECONNREFUSED 10.0.0.5:8000")),
    );

    const result = await forwardToBackend(CATALOG_REQUEST);
    const body = await result.text();

    expect(result.status).toBe(502);
    expect(body).toBe(JSON.stringify({ detail: "Backend unreachable" }));
    expect(body).not.toContain("ECONNREFUSED");
    expect(body).not.toContain("10.0.0.5");
  });

  it("returns 504 when the upstream call times out", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.reject(
        new DOMException("The operation was aborted.", "AbortError"),
      ),
    );

    const result = await forwardToBackend(CATALOG_REQUEST);

    expect(result.status).toBe(504);
    expect(await result.text()).toContain("timed out");
  });

  it("falls back to localhost when no backend url is configured", async () => {
    delete process.env.BACKEND_API_URL;
    const { calls } = captureFetch(jsonUpstream("[]", 200));

    await forwardToBackend(CATALOG_REQUEST);

    expect(calls[0]?.url).toBe("http://localhost:8000/api/aircraft");
  });
});
