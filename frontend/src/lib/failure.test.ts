import { describe, expect, it } from "vitest";

import { planFailure } from "./failure";

describe("plan failure (#95)", () => {
  it.each([
    "Backend returned status 502",
    "Backend returned status 503",
    "Request timed out",
    "Failed to fetch",
  ])("reads %s as the backend not answering", (error) => {
    const failure = planFailure("plan", error);
    expect(failure.title).toBe("Planner backend not answering");
    expect(failure.detail).toContain("Nothing was computed or recorded.");
    expect(failure.raw).toBe(error);
  });

  it("names a refused key apart from a backend that is down", () => {
    expect(planFailure("plan", "Backend returned status 401").title).toBe(
      "Planner refused this browser's key",
    );
  });

  it("names rejected inputs", () => {
    expect(planFailure("plan", "Backend returned status 422").title).toBe(
      "Planner rejected these inputs",
    );
  });

  it("says an unrecorded signature was not recorded", () => {
    const failure = planFailure("ack", "Backend returned status 503");
    expect(failure.detail).toContain("The signature was not recorded.");
  });
});
