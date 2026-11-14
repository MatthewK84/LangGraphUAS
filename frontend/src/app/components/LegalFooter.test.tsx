// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN } from "@/test/fixtures";
import { stubBackend } from "@/test/planner";

import MissionPlanner from "../page";

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

describe("legal footer (#117)", () => {
  it("disclaims endorsement and authorisation, with no third-party logo", () => {
    stubBackend(ADVISORY_PLAN);
    render(<MissionPlanner />);
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent(/MIT licence/i);
    expect(footer).toHaveTextContent(/reference data/i);
    expect(footer).toHaveTextContent(/not endorsement/i);
    expect(footer).toHaveTextContent(/not a flight authorisation/i);
    expect(footer.querySelector("img")).toBeNull();
    expect(footer.querySelector("svg")).toBeNull();
    expect(scrollingAncestor(footer)).toBeNull();
  });
});
