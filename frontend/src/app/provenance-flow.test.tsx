// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN } from "@/test/fixtures";
import { analyzeMission, stubBackend } from "@/test/planner";

import MissionPlanner from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openBasis(
  label: string,
): Promise<ReturnType<typeof userEvent.setup>> {
  stubBackend(ADVISORY_PLAN);
  render(<MissionPlanner />);
  const user = userEvent.setup();
  await analyzeMission(user);
  const row = (await screen.findByText(label)).closest("tr");
  if (row === null) {
    throw new Error(`no row for ${label}`);
  }
  await user.click(within(row).getByRole("button"));
  return user;
}

describe("provenance drawer (#96)", () => {
  it("traces a datasheet watt-hour to the URL it was read from", async () => {
    await openBasis("Usable capacity");
    const drawer = screen.getByRole("region", {
      name: "Provenance: Usable capacity",
    });
    const link = within(drawer).getByRole("link", {
      name: "freeflysystems.com/alta-x/specs",
    });
    expect(link.getAttribute("href")).toBe(
      "https://freeflysystems.com/alta-x/specs",
    );
    expect(link.getAttribute("rel")).toContain("noopener");
    within(drawer).getByText("aircraft.battery_wh");
    within(drawer).getByText("2026-01-05");
  });

  it("labels the estimate and the unrecorded field behind a watt", async () => {
    await openBasis("Hover power (corrected)");
    const drawer = screen.getByRole("region", {
      name: "Provenance: Hover power (corrected)",
    });
    within(drawer).getByText("Estimate");
    within(drawer).getByText("Not recorded");
    within(drawer).getByText(/Scaled from all-up mass/);
    expect(within(drawer).queryByRole("link")).toBeNull();
  });

  it("closes on Escape and gives focus back to the figure", async () => {
    const user = await openBasis("Usable capacity");
    const row = screen.getByText("Usable capacity").closest("tr");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: /^Provenance:/ })).toBeNull();
    expect(document.activeElement).toBe(
      row === null ? null : within(row).getByRole("button"),
    );
  });
});
