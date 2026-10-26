import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CATALOG_TIMEOUT_MS } from "./backend";
import {
  SESSION_COOKIE,
  forwardForBrowser,
  isSameOrigin,
  newSessionId,
  readSessionId,
  sessionCookie,
  sessionKey,
} from "./session";

const SECRET = "test-only-session-secret-0123456789abcdef";
const SESSION_A = "A".repeat(43);
const SESSION_B = "b".repeat(43);
// Shared with backend/tests/test_session_keys.py: both servers must derive
// the same key, or no browser can sign in.
const VECTOR_KEY =
  "session.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA." +
  "c3543da27fae09625f09f2a3106025813d7ea42b0d8924bb8e08786a76ee710b";
const ORIGIN = "http://localhost:3000";

const PLAN = {
  path: "/api/plan",
  method: "POST",
  timeoutMs: CATALOG_TIMEOUT_MS,
  requestId: null,
  body: "{}",
} as const;
const READ = {
  path: "/api/plan/t-1",
  method: "GET",
  timeoutMs: CATALOG_TIMEOUT_MS,
  requestId: null,
} as const;

function browser(
  method: "GET" | "POST",
  headers: Record<string, string> = {},
  url = `${ORIGIN}/api/plan`,
): Request {
  return new Request(url, { method, headers });
}

function upstreamKeys(): string[] {
  const keys: string[] = [];
  vi.stubGlobal("fetch", (_url: string, init: RequestInit) => {
    keys.push((init.headers as Record<string, string>)["X-API-Key"] ?? "");
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  return keys;
}

function cookieId(response: Response): string | null {
  const header = response.headers.get("Set-Cookie");
  return readSessionId(header);
}

describe("session identity", () => {
  it("derives the same key the backend checks", () => {
    expect(sessionKey(SECRET, SESSION_A)).toBe(VECTOR_KEY);
  });

  it("mints at least 128 random bits as base64url", () => {
    const first = newSessionId();
    expect(first).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(newSessionId()).not.toBe(first);
  });

  it("reads its own cookie among others and refuses a malformed one", () => {
    expect(readSessionId(`a=1; ${SESSION_COOKIE}=${SESSION_A}; b=2`)).toBe(
      SESSION_A,
    );
    expect(readSessionId(`${SESSION_COOKIE}=short`)).toBeNull();
    expect(readSessionId(`${SESSION_COOKIE}=${"x".repeat(40)}.!!`)).toBeNull();
    expect(readSessionId(null)).toBeNull();
  });

  it("sets an httpOnly, SameSite=Strict cookie, Secure over HTTPS", () => {
    const plain = sessionCookie(SESSION_A, false);
    expect(plain).toContain(`${SESSION_COOKIE}=${SESSION_A}`);
    expect(plain).toContain("HttpOnly");
    expect(plain).toContain("SameSite=Strict");
    expect(plain).toContain("Path=/");
    expect(plain).not.toContain("Secure");
    expect(sessionCookie(SESSION_A, true)).toContain("; Secure");
  });

  it("accepts only an Origin naming this host", () => {
    expect(isSameOrigin(browser("POST", { origin: ORIGIN }))).toBe(true);
    expect(
      isSameOrigin(browser("POST", { origin: "https://evil.example" })),
    ).toBe(false);
    expect(isSameOrigin(browser("POST"))).toBe(false);
    expect(
      isSameOrigin(
        browser("POST", {
          origin: "https://dash.example",
          "x-forwarded-host": "dash.example",
        }),
      ),
    ).toBe(true);
  });
});

describe("forwardForBrowser", () => {
  beforeEach(() => {
    process.env.BACKEND_API_URL = "http://backend.test:8000";
    process.env.BACKEND_SESSION_SECRET = SECRET;
    delete process.env.BACKEND_API_KEY;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete process.env.BACKEND_API_URL;
    delete process.env.BACKEND_SESSION_SECRET;
    delete process.env.BACKEND_API_KEY;
  });

  it("gives a new browser its own session and signs for it", async () => {
    const keys = upstreamKeys();

    const response = await forwardForBrowser(browser("GET"), READ);
    const minted = cookieId(response);

    expect(minted).not.toBeNull();
    expect(keys).toEqual([sessionKey(SECRET, minted ?? "")]);
  });

  it("keeps a returning browser's session", async () => {
    const keys = upstreamKeys();

    const response = await forwardForBrowser(
      browser("GET", { cookie: `${SESSION_COOKIE}=${SESSION_A}` }),
      READ,
    );

    expect(response.headers.get("Set-Cookie")).toBeNull();
    expect(keys).toEqual([sessionKey(SECRET, SESSION_A)]);
  });

  it("presents two browsers to the backend as two operators", async () => {
    const keys = upstreamKeys();

    await forwardForBrowser(
      browser("GET", { cookie: `${SESSION_COOKIE}=${SESSION_A}` }),
      READ,
    );
    await forwardForBrowser(
      browser("GET", { cookie: `${SESSION_COOKIE}=${SESSION_B}` }),
      READ,
    );

    expect(keys[0]).not.toBe(keys[1]);
  });

  it("never hands the browser the secret or a key", async () => {
    upstreamKeys();

    const response = await forwardForBrowser(browser("GET"), READ);
    const exposed = `${await response.text()} ${JSON.stringify([...response.headers])}`;
    const minted = cookieId(response) ?? "";

    expect(exposed).not.toContain(SECRET);
    expect(exposed).not.toContain(
      sessionKey(SECRET, minted).split(".").pop() ?? "",
    );
  });

  it("refuses a state change from another origin without calling the backend", async () => {
    const keys = upstreamKeys();

    const forged = await forwardForBrowser(
      browser("POST", {
        origin: "https://evil.example",
        cookie: `${SESSION_COOKIE}=${SESSION_A}`,
      }),
      PLAN,
    );
    const bare = await forwardForBrowser(browser("POST"), PLAN);

    expect(forged.status).toBe(403);
    expect(bare.status).toBe(403);
    expect(keys).toEqual([]);
  });

  it("forwards a same-origin state change", async () => {
    const keys = upstreamKeys();

    const response = await forwardForBrowser(
      browser("POST", {
        origin: ORIGIN,
        cookie: `${SESSION_COOKIE}=${SESSION_A}`,
      }),
      PLAN,
    );

    expect(response.status).toBe(200);
    expect(keys).toEqual([sessionKey(SECRET, SESSION_A)]);
  });

  it("keeps the single server key when no session secret is set", async () => {
    delete process.env.BACKEND_SESSION_SECRET;
    process.env.BACKEND_API_KEY = "shared-key";
    const keys = upstreamKeys();

    const response = await forwardForBrowser(browser("GET"), READ);

    expect(keys).toEqual(["shared-key"]);
    expect(response.headers.get("Set-Cookie")).toBeNull();
  });
});

describe("where the secret can be read", () => {
  const SRC = join(__dirname, "..", "..");

  function sources(dir: string): string[] {
    return readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) {
        return sources(path);
      }
      return /\.tsx?$/.test(name) && !name.endsWith(".test.ts") ? [path] : [];
    });
  }

  it("reads backend secrets only in src/lib/server", () => {
    const readers = sources(SRC)
      .filter((path) =>
        /process\.env\.BACKEND_/.test(readFileSync(path, "utf8")),
      )
      .map((path) => relative(SRC, path));
    expect(readers.every((path) => path.startsWith("lib/server/"))).toBe(true);
  });

  it("imports src/lib/server only from API route handlers", () => {
    const importers = sources(SRC)
      .filter((path) => readFileSync(path, "utf8").includes("@/lib/server/"))
      .map((path) => relative(SRC, path));
    expect(importers.length).toBeGreaterThan(0);
    expect(
      importers.every((path) => /^app\/api\/.*route\.ts$/.test(path)),
    ).toBe(true);
  });

  it("routes every proxied call through the browser session", () => {
    const routes = sources(join(SRC, "app", "api"));
    expect(routes.length).toBeGreaterThan(0);
    for (const path of routes) {
      const text = readFileSync(path, "utf8");
      expect(text, relative(SRC, path)).toContain("forwardForBrowser(");
      expect(text, relative(SRC, path)).not.toContain("forwardToBackend(");
    }
  });
});
