import { expect, test } from "vitest";

import { blockerReason } from "./blockers";

test("the stale snapshot blocker tells the operator why operational is refused", () => {
  const reason = blockerReason("BLUE_LIST_SNAPSHOT_STALE");
  expect(reason).toMatch(/older than the configured maximum age/i);
  expect(reason).toMatch(/bluelist\.dcma\.mil/i);
});

test("the lab-configuration blocker names the only pair in scope", () => {
  const reason = blockerReason("CONFIGURATION_NOT_LAB_OPERATIONAL");
  expect(reason).toMatch(/Freefly Astro Max/);
  expect(reason).toMatch(/Sony ILX-LR1/);
});
