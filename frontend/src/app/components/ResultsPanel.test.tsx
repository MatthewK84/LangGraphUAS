// @vitest-environment jsdom
import { cleanup, render, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
