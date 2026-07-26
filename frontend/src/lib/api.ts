// Typed API client. The base URL comes from the environment so the same build
// runs against local, staging, and production backends (no hardcoded host).

import type {
  AircraftSummary,
  ApiResult,
  MissionRequest,
  PayloadSummary,
  PlanResult,
} from "./types";

const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_KEY: string = process.env.NEXT_PUBLIC_API_KEY ?? "";
const REQUEST_TIMEOUT_MS = 45_000;
const CATALOG_TIMEOUT_MS = 15_000;

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY.length > 0) {
    headers["X-API-Key"] = API_KEY;
  }
  return headers;
}

function describeError(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "Request timed out";
  }
  return error instanceof Error ? error.message : "Unknown network error";
}

async function request<T>(
  path: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, timeoutMs);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: buildHeaders(),
      signal: controller.signal,
    });
    if (!response.ok) {
      return { ok: false, error: `Backend returned status ${String(response.status)}` };
    }
    const data = (await response.json()) as T;
    return { ok: true, data };
  } catch (error: unknown) {
    return { ok: false, error: describeError(error) };
  } finally {
    clearTimeout(timer);
  }
}

export async function planMission(body: MissionRequest): Promise<ApiResult<PlanResult>> {
  return request<PlanResult>(
    "/api/plan",
    { method: "POST", body: JSON.stringify(body) },
    REQUEST_TIMEOUT_MS,
  );
}

export async function fetchAircraft(): Promise<ApiResult<AircraftSummary[]>> {
  return request<AircraftSummary[]>("/api/aircraft", { method: "GET" }, CATALOG_TIMEOUT_MS);
}

export async function fetchPayloads(): Promise<ApiResult<PayloadSummary[]>> {
  return request<PayloadSummary[]>("/api/payloads", { method: "GET" }, CATALOG_TIMEOUT_MS);
}
