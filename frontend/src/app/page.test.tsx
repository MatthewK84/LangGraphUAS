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
