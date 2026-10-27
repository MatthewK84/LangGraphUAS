/**
 * The UI cannot display an estimate as a measured watt (#79).
 *
 * Every W and Wh figure the dashboard shows goes through `figureTag`, which
 * reads the backend's per-figure provenance. A figure the backend did not
 * label is shown as unverified, never as nothing.
 */

import { describe, expect, it } from "vitest";

import { basisEntries, figureTag } from "@/lib/provenance";
import { CITED_BATTERY } from "@/test/fixtures";
import type { NumberProvenance } from "@/lib/types";

const derived: NumberProvenance = {
  source: "derived",
  confidence: "medium",
  operational_grade: false,
  inputs: ["aircraft.hover_power_w"],
  basis: [],
};

const datasheet: NumberProvenance = {
  source: "datasheet",
  confidence: "high",
  operational_grade: true,
  inputs: ["aircraft.hover_power_w"],
  basis: [],
};

describe("figureTag", () => {
  it("labels an estimate-grade watt with its source and confidence", () => {
    expect(
      figureTag(
        { effective_hover_power_w: derived },
        "effective_hover_power_w",
      ),
    ).toEqual({ label: "derived, medium confidence", operationalGrade: false });
  });

  it("labels an operational-grade watt by its source alone", () => {
    expect(
      figureTag(
        { effective_hover_power_w: datasheet },
        "effective_hover_power_w",
      ),
    ).toEqual({ label: "datasheet", operationalGrade: true });
  });

  it("calls a figure with no provenance unverified, not measured", () => {
    expect(figureTag({}, "energy_required_wh")).toEqual({
      label: "unverified",
      operationalGrade: false,
    });
  });
});

describe("basisEntries (#96)", () => {
  const entry = (basis: NumberProvenance["basis"]): NumberProvenance => ({
    ...derived,
    basis,
  });

  it("links a cited datasheet field out to its URL", () => {
    const [battery] = basisEntries(entry([CITED_BATTERY]));
    expect(battery?.citation).toEqual({
      href: "https://freeflysystems.com/alta-x/specs",
      text: "freeflysystems.com/alta-x/specs",
    });
    expect(battery?.sourceLabel).toBe("Datasheet");
    expect(battery?.operationalGrade).toBe(true);
    expect(battery?.retrieved).toBe("2026-01-05");
  });

  it("labels an estimate as an estimate, and never as operational", () => {
    const [estimate] = basisEntries(
      entry([{ ...CITED_BATTERY, source: "estimate", source_url: null }]),
    );
    expect(estimate?.sourceLabel).toBe("Estimate");
    expect(estimate?.operationalGrade).toBe(false);
    expect(estimate?.citation).toBeNull();
  });

  it("says a field with no record is not recorded", () => {
    const [missing] = basisEntries(
      entry([{ ...CITED_BATTERY, source: "unknown", value: null, unit: null }]),
    );
    expect(missing?.sourceLabel).toBe("Not recorded");
  });

  it("links only http and https citations", () => {
    const [script] = basisEntries(
      entry([{ ...CITED_BATTERY, source_url: "javascript:alert(1)" }]),
    );
    expect(script?.citation).toBeNull();
  });

  it("shows a retrieval timestamp in UTC", () => {
    const [stamped] = basisEntries(
      entry([{ ...CITED_BATTERY, retrieved_at: "2026-01-05T14:03:00-05:00" }]),
    );
    expect(stamped?.retrieved).toBe("2026-01-05 19:03Z");
  });
});
