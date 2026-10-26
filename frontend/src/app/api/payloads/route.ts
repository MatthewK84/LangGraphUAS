import { CATALOG_TIMEOUT_MS } from "@/lib/server/backend";
import { forwardForBrowser } from "@/lib/server/session";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  return forwardForBrowser(request, {
    path: "/api/payloads",
    method: "GET",
    timeoutMs: CATALOG_TIMEOUT_MS,
    requestId: request.headers.get("X-Request-ID"),
  });
}
