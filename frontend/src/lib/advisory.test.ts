import { describe, expect, it } from "vitest";

import { ADVISORY_PLAN, OPERATIONAL_PLAN, REPLAN } from "@/test/fixtures";

import { advisoryNotice } from "./advisory";

describe("advisory notice (#91)", () => {
  it("is absent before there is a plan", () => {
    expect(advisoryNotice(null, null)).toBeNull();
  });

  it("is present for an advisory plan, with its mode and weather source", () => {
    expect(advisoryNotice(ADVISORY_PLAN, null)).toEqual({
      mode: "advisory",
      weatherSource: "fallback",
      replanAlerts: null,
    });
  });

  it("is absent for an operational plan with no replan", () => {
    expect(advisoryNotice(OPERATIONAL_PLAN, null)).toBeNull();
  });

  it("stays present after a clean replan of an advisory plan", () => {
    const clean = { ...REPLAN, operational_ok: true, alerts: [] };
    expect(advisoryNotice(ADVISORY_PLAN, clean)?.mode).toBe("advisory");
  });

  it("appears when a replan of an operational plan raises any alert", () => {
    expect(advisoryNotice(OPERATIONAL_PLAN, REPLAN)).toEqual({
      mode: "advisory",
      weatherSource: "live",
      replanAlerts: 1,
    });
  });

  it("treats a plan with no sealed assessment as advisory", () => {
    const unsealed = { ...OPERATIONAL_PLAN, assessment: null };
    expect(advisoryNotice(unsealed, null)?.mode).toBe("advisory");
  });
});
