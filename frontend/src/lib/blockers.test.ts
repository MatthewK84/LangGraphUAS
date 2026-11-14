import { expect, test } from "vitest";

import { blockerReason } from "./blockers";

test("the stale snapshot blocker tells the operator why operational is refused", () => {
  const reason = blockerReason("BLUE_LIST_SNAPSHOT_STALE");
  expect(reason).toMatch(/older than the configured maximum age/i);
  expect(reason).toMatch(/bluelist\.dcma\.mil/i);
});
