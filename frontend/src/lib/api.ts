// Typed API client. The base URL comes from the environment so the same build
// runs against local, staging, and production backends (no hardcoded host).

import type { ApiResult, MissionRequest, PlanResult } from "./types";

const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_KEY: string = process.env.NEXT_PUBLIC_API_KEY ?? "";
const REQUEST_TIMEOUT_MS = 45_000;

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY.length > 0) {
    headers["X-API-Key"] = API_KEY;
  }
  return headers;
}

export async function planMission(request: MissionRequest): Promise<ApiResult<PlanResult>> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/api/plan`, {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(request),
      signal: controller.signal,
    });
    if (!response.ok) {
      return { ok: false, error: `Backend returned status ${String(response.status)}` };
    }
    const data = (await response.json()) as PlanResult;
    return { ok: true, data };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Unknown network error";
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}
