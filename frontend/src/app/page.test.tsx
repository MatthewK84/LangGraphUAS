// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN, OPERATIONAL_PLAN } from "@/test/fixtures";
import { analyzeMission, stubBackend } from "@/test/planner";

import MissionPlanner from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SCROLLS = /\boverflow-(y-)?(auto|scroll)\b/;

function scrollingAncestor(element: HTMLElement): HTMLElement | null {
  let node = element.parentElement;
  while (node !== null) {
    if (SCROLLS.test(node.className)) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

describe("planner page advisory banner (#91)", () => {
  it("shows the banner outside every scrolling panel for an advisory plan", async () => {
    stubBackend(ADVISORY_PLAN);
    render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    const banner = await screen.findByRole("region", {
      name: "Advisory: not a clearance",
    });
    expect(scrollingAncestor(banner)).toBeNull();
  });

  it("shows no banner for an operational plan", async () => {
    stubBackend(OPERATIONAL_PLAN);
    render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    await screen.findByText("CLEAR TO LAUNCH (GO)");
    expect(
      screen.queryByRole("region", { name: "Advisory: not a clearance" }),
    ).toBeNull();
  });
});

describe("planner page shell", () => {
  // Screen-reader-only table headers are absolutely positioned. Inside a
  // scrolling panel that is not a containing block they escape its clip and
  // grow the document, so the fixed shell scrolls as a whole on short screens.
  it("makes every scrolling panel contain its absolutely positioned content", async () => {
    stubBackend(OPERATIONAL_PLAN);
    const { container } = render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    await screen.findByText("CLEAR TO LAUNCH (GO)");
    const panels = [...container.querySelectorAll<HTMLElement>("*")].filter(
      (node) => SCROLLS.test(node.className),
    );
    expect(panels.length).toBeGreaterThanOrEqual(3);
    for (const panel of panels) {
      expect(panel.className).toMatch(/\brelative\b/);
    }
  });
});
