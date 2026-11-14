// @vitest-environment jsdom
import { cleanup, render, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Assessment, PlanResult } from "@/lib/types";
import { ADVISORY_PLAN } from "@/test/fixtures";

import { ResultsPanel } from "./ResultsPanel";

afterEach(cleanup);

function figureRows(): readonly HTMLElement[] {
  const view = render(
    <ResultsPanel loading={false} error={null} result={ADVISORY_PLAN} />,
  );
  return view.getAllByRole("row").filter((row) => {
    const unit = row.querySelectorAll("td")[1]?.textContent;
    return unit === "W" || unit === "Wh";
  });
}

describe("results panel", () => {
  it("renders every W and Wh figure with its basis beside it (#79)", () => {
    const rows = figureRows();
    expect(rows).toHaveLength(8);
    for (const row of rows) {
      const basis = row.querySelectorAll("td")[2];
      expect(basis?.textContent).toMatch(
        /^(datasheet|estimate, low confidence)$/,
      );
    }
  });

  it("marks an estimate apart from an operational-grade figure", () => {
    const capacity = figureRows().find((row) =>
      within(row).queryByText("Usable capacity"),
    );
    const hover = figureRows().find((row) =>
      within(row).queryByText("Hover power (corrected)"),
    );
    expect(capacity?.textContent).toContain("datasheet");
    expect(hover?.querySelector(".text-caution")?.textContent).toBe(
      "estimate, low confidence",
    );
  });
});

describe("advisory blockers", () => {
  it("shows an operator-facing reason next to a stale Blue UAS snapshot code", () => {
    const base = ADVISORY_PLAN.assessment;
    if (base === null) {
      throw new Error("advisory fixture must include an assessment");
    }
    const assessment: Assessment = {
      decision: base.decision,
      reasons: base.reasons,
      mode: base.mode,
      blockers: ["BLUE_LIST_SNAPSHOT_STALE"],
      inputs_hash: base.inputs_hash,
      calculator_version: base.calculator_version,
    };
    const result: PlanResult = { ...ADVISORY_PLAN, assessment };
    const view = render(
      <ResultsPanel loading={false} error={null} result={result} />,
    );
    const note = view.getByRole("note");
    expect(note.textContent).toMatch(/BLUE_LIST_SNAPSHOT_STALE/);
    expect(note.textContent).toMatch(/older than the configured maximum age/);
    expect(note.textContent).toMatch(/bluelist\.dcma\.mil/);
  });
});

describe("empty assessment", () => {
  it("states that operational mode is off by default and names the lab pair", () => {
    const view = render(
      <ResultsPanel loading={false} error={null} result={null} />,
    );
    expect(view.container.textContent).toMatch(
      /Operational mode is off by default/,
    );
    expect(view.container.textContent).toMatch(/Freefly Astro Max/);
    expect(view.container.textContent).toMatch(/Sony ILX-LR1/);
  });
});
