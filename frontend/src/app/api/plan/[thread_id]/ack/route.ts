import { PLAN_TIMEOUT_MS } from "@/lib/server/backend";
import { forwardForBrowser } from "@/lib/server/session";

export const dynamic = "force-dynamic";

interface RouteContext {
  readonly params: { readonly thread_id: string };
}

export async function POST(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return new Response(
      JSON.stringify({ detail: "Could not read request body" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }
  // Encoded so a crafted thread id cannot escape the intended backend path.
  const threadId: string = encodeURIComponent(context.params.thread_id);
  return forwardForBrowser(request, {
    path: `/api/plan/${threadId}/ack`,
    method: "POST",
    timeoutMs: PLAN_TIMEOUT_MS,
    requestId: request.headers.get("X-Request-ID"),
    body,
  });
}
