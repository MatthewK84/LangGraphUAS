// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN, BRIEFED_PLAN } from "@/test/fixtures";
import { analyzeMission, stubBackend } from "@/test/planner";

import { metadata } from "./layout";
import MissionPlanner from "./page";

// The document's language and title belong to the root layout, which jsdom
// does not render; set them as layout.tsx does so axe checks the real page.
beforeEach(() => {
  document.documentElement.lang = "en";
  document.title = typeof metadata.title === "string" ? metadata.title : "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/**
 * axe against the whole planner page. jsdom lays nothing out, so axe cannot
 * measure color contrast here; the NO-GO treatment's contrast is pinned
 * against the tokens in src/lib/contrast.test.ts instead.
 */
async function violations(): Promise<string[]> {
  const report = await axe.run(document, {
    rules: { "color-contrast": { enabled: false } },
  });
  return report.violations.map(
    (violation) =>
      `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`,
  );
}

describe("axe on the planner page (#98)", () => {
  it("finds nothing on the empty page", async () => {
    stubBackend(ADVISORY_PLAN);
    render(<MissionPlanner />);
    await screen.findByRole("option", { name: "DJI Matrice 350 RTK" });
    expect(await violations()).toEqual([]);
  });

  it("finds nothing while an assessment awaits its signature", async () => {
    stubBackend(ADVISORY_PLAN);
    render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    await screen.findByRole("region", { name: "Assessment review" });
    expect(await violations()).toEqual([]);
  });

  it("finds nothing with the skip link focused", async () => {
    stubBackend(ADVISORY_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    await screen.findByRole("region", { name: "Assessment review" });
    await user.tab();
    expect(document.activeElement?.textContent).toBe("Skip to sign-off");
    expect(await violations()).toEqual([]);
  });

  it("finds nothing once signed, with the provenance drawer open", async () => {
    stubBackend(ADVISORY_PLAN, BRIEFED_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    const card = await screen.findByRole("region", {
      name: "Assessment review",
    });
    await user.click(within(card).getByRole("checkbox"));
    await user.click(
      within(card).getByRole("button", {
        name: "Acknowledge and generate brief",
      }),
    );
    await screen.findByRole("heading", { name: "Safety officer brief" });
    const [basis] = screen.getAllByRole("button", {
      name: /show the provenance of/,
    });
    if (basis === undefined) {
      throw new Error("no figure offers its provenance");
    }
    await user.click(basis);
    await screen.findByRole("region", { name: /^Provenance: / });
    expect(await violations()).toEqual([]);
  });
});
