import { afterEach, expect, test, vi } from "vitest";

const forward = vi.hoisted(() => vi.fn(() => Promise.resolve(new Response("ok"))));

vi.mock("@/lib/server/session", () => ({
  forwardForBrowser: forward,
}));

afterEach(() => {
  forward.mockClear();
});

test("GET awaits route params before forwarding the thread id", async () => {
  const { GET } = await import("./route");
  const request = new Request("http://localhost/api/plan/abc-1", {
    headers: { "X-Request-ID": "req-1" },
  });
  const response = await GET(request, {
    params: Promise.resolve({ thread_id: "abc-1" }),
  });
  expect(response.status).toBe(200);
  expect(forward).toHaveBeenCalledOnce();
  const call = forward.mock.calls[0] as unknown as [
    Request,
    { path: string; method: string },
  ];
  expect(call[1].path).toBe("/api/plan/abc-1");
  expect(call[1].method).toBe("GET");
});
