/**
 * The UI cannot display an estimate as a measured watt (#79).
 *
 * Every W and Wh figure the dashboard shows goes through `figureTag`, which
 * reads the backend's per-figure provenance. A figure the backend did not
 * label is shown as unverified, never as nothing.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { figureTag } from "@/lib/provenance";
import type { NumberProvenance } from "@/lib/types";

const derived: NumberProvenance = {
  source: "derived",
  confidence: "medium",
  operational_grade: false,
  inputs: ["aircraft.hover_power_w"],
};

const datasheet: NumberProvenance = {
  source: "datasheet",
  confidence: "high",
  operational_grade: true,
  inputs: ["aircraft.hover_power_w"],
};

describe("figureTag", () => {
  it("labels an estimate-grade watt with its source and confidence", () => {
    expect(
      figureTag({ effective_hover_power_w: derived }, "effective_hover_power_w"),
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

describe("results panel", () => {
  it("renders no W or Wh figure except through Figure", () => {
    const panel = readFileSync(
      join(process.cwd(), "src", "app", "components", "ResultsPanel.tsx"),
      "utf8",
    );

    expect(panel.match(/\}\s*Wh?\s*</g) ?? []).toEqual([]);
    expect(panel.match(/<Figure\b/g)?.length).toBe(8);
  });
});
