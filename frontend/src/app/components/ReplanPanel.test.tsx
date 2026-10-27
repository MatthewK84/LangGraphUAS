// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OPERATIONAL_PLAN, REPLAN, REPLAN_SNAPSHOT } from "@/test/fixtures";

import { ReplanPanel } from "./ReplanPanel";

afterEach(cleanup);

function panel(): HTMLElement {
  render(
    <ReplanPanel
      plan={OPERATIONAL_PLAN}
      sent={REPLAN_SNAPSHOT}
      replan={REPLAN}
    />,
  );
  return screen.getByRole("region", { name: "Replan against live telemetry" });
}

function cells(region: HTMLElement, label: string): readonly string[] {
  const row = within(region).getByRole("row", { name: new RegExp(label) });
  return within(row)
    .getAllByRole("cell")
    .map((cell) => cell.textContent ?? "");
}

describe("replan residual panel (#94)", () => {
  it("keeps the briefed figure next to the live one", () => {
    expect(cells(panel(), "Margin after mission")).toEqual([
      "41.7",
      "44.54",
      "+2.84",
      "Wh",
    ]);
  });

  it("compares wind and state of charge as well as energy", () => {
    const region = panel();
    expect(cells(region, "Wind")).toEqual(["3.9", "6.1", "+2.2", "m/s"]);
    expect(cells(region, "State of charge")).toEqual(["100", "42", "-58", "%"]);
  });

  it("calls a replan with one watch alert advisory", () => {
    const region = panel();
    expect(within(region).getByText("Advisory only")).toBeDefined();
    expect(within(region).getByText("advisory")).toBeDefined();
  });

  it("lists each alert by code, configured label and message", () => {
    const region = panel();
    expect(within(region).getByText("SOC_STALE")).toBeDefined();
    expect(within(region).getByText("Telemetry too old")).toBeDefined();
    expect(within(region).getByText(/beyond the 30.0 s limit/)).toBeDefined();
  });
});
