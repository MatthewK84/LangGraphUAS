import { PLAN_TIMEOUT_MS, forwardToBackend } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

interface RouteContext {
  readonly params: { readonly thread_id: string };
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  // Encoded so a crafted thread id cannot escape the intended backend path.
  const threadId: string = encodeURIComponent(context.params.thread_id);
  return forwardToBackend({
    path: `/api/plan/${threadId}`,
    method: "GET",
    timeoutMs: PLAN_TIMEOUT_MS,
    requestId: request.headers.get("X-Request-ID"),
  });
}
