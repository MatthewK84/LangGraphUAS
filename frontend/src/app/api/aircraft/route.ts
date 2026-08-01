import { CATALOG_TIMEOUT_MS, forwardToBackend } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  return forwardToBackend({
    path: "/api/aircraft",
    method: "GET",
    timeoutMs: CATALOG_TIMEOUT_MS,
    requestId: request.headers.get("X-Request-ID"),
  });
}
