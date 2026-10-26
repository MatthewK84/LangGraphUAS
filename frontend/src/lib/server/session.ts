// Anonymous per-browser operators (#82).
//
// Each browser gets a random session id in an httpOnly cookie. When
// BACKEND_SESSION_SECRET is set, the proxy presents the backend with
// session.<id>.<HMAC-SHA256(secret, id)>, which the backend verifies and treats
// as that browser's own operator. The secret, and every key derived from it,
// stay in this process: the browser holds only its own session id.

import { createHmac, randomBytes } from "node:crypto";

import { type BackendRequest, forwardToBackend } from "./backend";

export const SESSION_COOKIE = "suas_session";
// Matches checkpoint retention: a thread outlives its cookie by nothing.
const SESSION_MAX_AGE_S = String(30 * 24 * 60 * 60);
const SESSION_ID = /^[A-Za-z0-9_-]{43}$/;

/** Return a fresh 256-bit session id, base64url encoded. */
export function newSessionId(): string {
  return randomBytes(32).toString("base64url");
}

/** Return the session id in a Cookie (or Set-Cookie) header, if well formed. */
export function readSessionId(header: string | null): string | null {
  const prefix = `${SESSION_COOKIE}=`;
  const entry = (header ?? "")
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  const value = entry?.slice(prefix.length) ?? "";
  return SESSION_ID.test(value) ? value : null;
}

/** Return the Set-Cookie value that issues a session. */
export function sessionCookie(id: string, secure: boolean): string {
  const attributes = `Path=/; Max-Age=${SESSION_MAX_AGE_S}; HttpOnly; SameSite=Strict`;
  return `${SESSION_COOKIE}=${id}; ${attributes}${secure ? "; Secure" : ""}`;
}

/** Return the backend key a session presents. Mirrors suas.api.security. */
export function sessionKey(secret: string, id: string): string {
  const mac = createHmac("sha256", secret).update(id).digest("hex");
  return `session.${id}.${mac}`;
}

function requestHost(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-host");
  return forwarded ?? request.headers.get("host") ?? new URL(request.url).host;
}

function isSecureRequest(request: Request): boolean {
  const proto = request.headers.get("x-forwarded-proto")?.split(",")[0];
  return (proto ?? new URL(request.url).protocol.replace(":", "")) === "https";
}

/** Return whether a request's Origin names this host. A missing Origin fails. */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (origin === null) {
    return false;
  }
  try {
    return new URL(origin).host === requestHost(request);
  } catch {
    return false;
  }
}

function refused(): Response {
  return new Response(
    JSON.stringify({ detail: "Cross-origin request refused" }),
    { status: 403, headers: { "Content-Type": "application/json" } },
  );
}

/**
 * Forward a browser's request as that browser's own operator.
 *
 * A state change must carry this host's Origin (CSRF). Without a session
 * secret the proxy keeps the single server key and issues no cookie.
 */
export async function forwardForBrowser(
  incoming: Request,
  request: BackendRequest,
): Promise<Response> {
  if (request.method === "POST" && !isSameOrigin(incoming)) {
    return refused();
  }
  const secret = process.env.BACKEND_SESSION_SECRET ?? "";
  if (secret.length === 0) {
    return forwardToBackend(request);
  }
  const existing = readSessionId(incoming.headers.get("cookie"));
  const id = existing ?? newSessionId();
  const response = await forwardToBackend({
    ...request,
    apiKey: sessionKey(secret, id),
  });
  if (existing === null) {
    response.headers.append(
      "Set-Cookie",
      sessionCookie(id, isSecureRequest(incoming)),
    );
  }
  return response;
}
