import { afterEach, expect, test, vi } from "vitest";

const forward = vi.hoisted(() =>
  vi.fn(() => Promise.resolve(new Response("ok"))),
);

vi.mock("@/lib/server/session", () => ({
  forwardForBrowser: forward,
}));

afterEach(() => {
  forward.mockClear();
});

test("POST awaits route params before forwarding the acknowledgement", async () => {
  const { POST } = await import("./route");
  const request = new Request("http://localhost/api/plan/abc-1/ack", {
    method: "POST",
    headers: { "X-Request-ID": "req-1", "Content-Type": "application/json" },
    body: '{"acknowledged":true}',
  });
  const response = await POST(request, {
    params: Promise.resolve({ thread_id: "abc-1" }),
  });
  expect(response.status).toBe(200);
  expect(forward).toHaveBeenCalledOnce();
  const call = forward.mock.calls[0] as unknown as [
    Request,
    { path: string; method: string; body: string },
  ];
  expect(call[1].path).toBe("/api/plan/abc-1/ack");
  expect(call[1].method).toBe("POST");
  expect(call[1].body).toBe('{"acknowledged":true}');
});
