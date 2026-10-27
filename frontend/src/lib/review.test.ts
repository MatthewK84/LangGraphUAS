import { describe, expect, it } from "vitest";

import { confirmBlocker } from "./review";

const CLEAR = {
  busy: false,
  advisory: true,
  understood: true,
  reviewedHash: "9f3c27a1d0b8",
  currentHash: "9f3c27a1d0b8",
  inputsEdited: false,
};

describe("confirm blocker (#92)", () => {
  it("allows a signature once every condition holds", () => {
    expect(confirmBlocker(CLEAR)).toBeNull();
  });

  it("blocks after any input edit, whatever else holds", () => {
    expect(confirmBlocker({ ...CLEAR, inputsEdited: true })).toBe(
      "Inputs edited since this assessment. Analyze again before signing.",
    );
  });

  it("blocks when the assessment is not the one that was displayed", () => {
    expect(confirmBlocker({ ...CLEAR, currentHash: "4b1e8d7c2a9f" })).toBe(
      "The assessment changed after it was shown. Review it again.",
    );
  });

  it("blocks an advisory plan until the operator says they understand", () => {
    expect(confirmBlocker({ ...CLEAR, understood: false })).toBe(
      "Tick the advisory acknowledgement to sign.",
    );
  });

  it("does not ask an operational plan for the advisory tick", () => {
    expect(
      confirmBlocker({ ...CLEAR, advisory: false, understood: false }),
    ).toBeNull();
  });

  it("blocks while a request is in flight", () => {
    expect(confirmBlocker({ ...CLEAR, busy: true })).toBe(
      "Waiting for the backend.",
    );
  });
});
