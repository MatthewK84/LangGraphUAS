import { PLAN_TIMEOUT_MS } from "@/lib/server/backend";
import { forwardForBrowser } from "@/lib/server/session";

export const dynamic = "force-dynamic";

/** Proxies a telemetry snapshot to the backend replan, under this browser's key. */
export async function POST(request: Request): Promise<Response> {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return new Response(
      JSON.stringify({ detail: "Could not read request body" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }
  return forwardForBrowser(request, {
    path: "/api/replan",
    method: "POST",
    timeoutMs: PLAN_TIMEOUT_MS,
    requestId: request.headers.get("X-Request-ID"),
    body,
  });
}
