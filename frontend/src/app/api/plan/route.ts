import { PLAN_TIMEOUT_MS, forwardToBackend } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return new Response(
      JSON.stringify({ detail: "Could not read request body" }),
      {
        status: 400,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
  return forwardToBackend({
    path: "/api/plan",
    method: "POST",
    timeoutMs: PLAN_TIMEOUT_MS,
    requestId: request.headers.get("X-Request-ID"),
    body,
  });
}
